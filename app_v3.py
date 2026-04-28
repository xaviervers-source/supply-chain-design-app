import pandas as pd
import streamlit as st
import unicodedata

from optimizer_v3 import extract_kpis, solve_design_model


st.set_page_config(page_title="Supply Chain Design", layout="wide")


def normalize_label(value):
    """Normalise un libelle pour comparer les colonnes sans accents ni casse."""
    text = str(value).strip().lower()
    text = unicodedata.normalize("NFKD", text)
    return "".join(character for character in text if not unicodedata.combining(character))


def normalize_site_name(value):
    """Normalise les noms de sites pour faire correspondre les deux fichiers."""
    return str(value).strip().upper()


def find_column(dataframe, expected_name):
    """Trouve une colonne meme si la casse ou les accents different."""
    expected_label = normalize_label(expected_name)
    for column in dataframe.columns:
        if normalize_label(column) == expected_label:
            return column
    return None


def read_cost_file(uploaded_file):
    """Lit le fichier Excel des couts et retourne sites, regions et couts."""
    cost_df = pd.read_excel(uploaded_file)
    site_column = find_column(cost_df, "Site")
    fixed_cost_column = find_column(cost_df, "Cout fixe")

    if site_column is None or fixed_cost_column is None:
        raise ValueError("Le fichier couts doit contenir les colonnes 'Site' et 'Cout fixe'.")

    regions = [
        column
        for column in cost_df.columns
        if column not in (site_column, fixed_cost_column)
    ]
    if not regions:
        raise ValueError("Le fichier couts doit contenir au moins une region.")

    if cost_df[site_column].isna().any():
        raise ValueError("La colonne 'Site' du fichier couts contient des valeurs vides.")

    if cost_df[[fixed_cost_column] + regions].isna().any().any():
        raise ValueError("Le fichier couts contient des couts fixes ou variables vides.")

    cost_df = cost_df.copy()
    cost_df[site_column] = cost_df[site_column].apply(normalize_site_name)
    cost_df = cost_df.rename(
        columns={
            site_column: "Site",
            fixed_cost_column: "Cout fixe",
        }
    )

    sites = cost_df["Site"].tolist()
    fixed_costs = {}
    variable_costs = {}

    for _, row in cost_df.iterrows():
        site = str(row["Site"])
        fixed_costs[site] = float(row["Cout fixe"])
        for region in regions:
            variable_costs[site, region] = float(row[region])

    return sites, regions, variable_costs, fixed_costs, cost_df


def read_capacity_file(uploaded_file):
    """Lit le fichier Excel des capacites et retourne un dictionnaire par site."""
    capacity_df = pd.read_excel(uploaded_file)
    site_column = find_column(capacity_df, "Site")
    capacity_column = find_column(capacity_df, "Capacite")

    if site_column is None or capacity_column is None:
        raise ValueError("Le fichier capacites doit contenir les colonnes 'Site' et 'Capacite'.")

    if capacity_df[[site_column, capacity_column]].isna().any().any():
        raise ValueError("Le fichier capacites contient des valeurs vides.")

    capacity_df = capacity_df.copy()
    capacity_df[site_column] = capacity_df[site_column].apply(normalize_site_name)
    capacity_df = capacity_df.rename(
        columns={
            site_column: "Site",
            capacity_column: "Capacite",
        }
    )

    capacities = {}
    for _, row in capacity_df.iterrows():
        site = str(row["Site"])
        capacity = float(row["Capacite"])
        capacities[site] = capacity

    return capacities, capacity_df


def validate_uploaded_data(
    sites,
    regions,
    variable_costs,
    capacities,
    demands,
    fixed_costs,
    scenario_name,
):
    """Controle les donnees avant d'appeler le solveur."""
    errors = []

    missing_capacity_sites = [site for site in sites if site not in capacities]
    if missing_capacity_sites:
        errors.append(
            "Sites presents dans le fichier couts mais absents du fichier capacites : "
            + ", ".join(missing_capacity_sites)
        )

    invalid_capacity_sites = [
        site for site, capacity in capacities.items() if capacity <= 0
    ]
    if invalid_capacity_sites:
        errors.append(
            "Les capacites doivent etre positives pour : "
            + ", ".join(invalid_capacity_sites)
        )

    missing_fixed_cost_sites = [
        site for site in sites if site not in fixed_costs
    ]
    invalid_fixed_cost_sites = [
        site for site, fixed_cost in fixed_costs.items() if fixed_cost < 0
    ]

    if missing_fixed_cost_sites:
        errors.append(
            "Couts fixes absents du fichier couts pour : "
            + ", ".join(missing_fixed_cost_sites)
        )
    if invalid_fixed_cost_sites:
        errors.append(
            "Les couts fixes ne peuvent pas etre negatifs pour : "
            + ", ".join(invalid_fixed_cost_sites)
        )

    for site in sites:
        for region in regions:
            if (site, region) not in variable_costs:
                errors.append(f"Cout variable manquant pour {site} -> {region}.")

    total_capacity = sum(capacities.get(site, 0) for site in sites)
    total_demand = sum(demands.values())
    if total_capacity < total_demand:
        errors.append(
            f"{scenario_name} - Capacite totale insuffisante : "
            f"{total_capacity:,.0f} disponible pour {total_demand:,.0f} demande."
        )

    return errors


def build_flow_dataframe(sites, regions, solution):
    """Transforme les flux du solveur en tableau lisible."""
    rows = []
    for site in sites:
        row = {"Site": site}
        total_site = 0
        for region in regions:
            flow = solution["flows"][site, region]
            row[region] = flow
            total_site += flow
        row["Total site"] = total_site
        rows.append(row)

    return pd.DataFrame(rows)


def build_site_status_dataframe(sites, solution):
    """Construit le tableau ouvert/ferme par site."""
    return pd.DataFrame(
        {
            "Site": sites,
            "Statut": [solution["site_status"][site] for site in sites],
        }
    )


def build_capacity_dataframe(sites, solution):
    """Construit le tableau d'utilisation des capacites."""
    rows = []
    for site in sites:
        summary = solution["site_summary"][site]
        rows.append(
            {
                "Site": site,
                "Capacite": summary["capacite"],
                "Volume": summary["volume"],
                "Taux utilisation": summary["taux_utilisation"],
                "Capacite restante": summary["capacite_restante"],
            }
        )

    return pd.DataFrame(rows)


def build_comparison_dataframe(scenario_1_solution, scenario_2_solution, sites):
    """Construit un tableau synthetique de comparaison entre deux scenarios."""
    scenario_1_kpis = extract_kpis(scenario_1_solution, sites)
    scenario_2_kpis = extract_kpis(scenario_2_solution, sites)

    return pd.DataFrame(
        [
            {
                "Scenario": "Scenario 1",
                "Statut": scenario_1_kpis["statut"],
                "Cout total": scenario_1_kpis["cout_total"],
                "Cout variable": scenario_1_kpis["cout_variable"],
                "Cout fixe": scenario_1_kpis["cout_fixe"],
                "Nombre sites ouverts": scenario_1_kpis["nombre_sites_ouverts"],
                "Sites ouverts": scenario_1_kpis["sites_ouverts"],
            },
            {
                "Scenario": "Scenario 2",
                "Statut": scenario_2_kpis["statut"],
                "Cout total": scenario_2_kpis["cout_total"],
                "Cout variable": scenario_2_kpis["cout_variable"],
                "Cout fixe": scenario_2_kpis["cout_fixe"],
                "Nombre sites ouverts": scenario_2_kpis["nombre_sites_ouverts"],
                "Sites ouverts": scenario_2_kpis["sites_ouverts"],
            },
        ]
    )


def build_site_comparison_dataframe(sites, scenario_1_solution, scenario_2_solution):
    """Compare les indicateurs de capacite site par site."""
    rows = []
    for site in sites:
        scenario_1_summary = scenario_1_solution["site_summary"][site]
        scenario_2_summary = scenario_2_solution["site_summary"][site]

        rows.append(
            {
                "Site": site,
                "Statut S1": scenario_1_solution["site_status"][site],
                "Statut S2": scenario_2_solution["site_status"][site],
                "Capacite utilisee S1": scenario_1_summary["volume"],
                "Capacite utilisee S2": scenario_2_summary["volume"],
                "Taux utilisation S1": scenario_1_summary["taux_utilisation"],
                "Taux utilisation S2": scenario_2_summary["taux_utilisation"],
                "Capacite restante S1": scenario_1_summary["capacite_restante"],
                "Capacite restante S2": scenario_2_summary["capacite_restante"],
            }
        )

    return pd.DataFrame(rows)


def display_solution(title, sites, regions, solution):
    """Affiche tous les resultats d'un scenario."""
    st.subheader(title)
    st.write(f"Statut du solveur : **{solution['status_name']}**")

    if not solution["has_solution"]:
        st.warning("Aucune solution exploitable n'a ete trouvee.")
        return

    metric_left, metric_middle, metric_right = st.columns(3)
    metric_left.metric("Cout total", f"{solution['total_cost']:,.2f}")
    metric_middle.metric("Cout variable", f"{solution['variable_cost']:,.2f}")
    metric_right.metric("Cout fixe", f"{solution['fixed_cost']:,.2f}")

    st.write("Sites ouverts / fermes")
    st.dataframe(
        build_site_status_dataframe(sites, solution),
        use_container_width=True,
    )

    st.write("Utilisation des capacites")
    capacity_result_df = build_capacity_dataframe(sites, solution)
    st.dataframe(
        capacity_result_df.style.format({"Taux utilisation": "{:.1%}"}),
        use_container_width=True,
    )


st.title("Supply Chain Design - Comparaison de scenarios")

st.write(
    "Chargez les fichiers Excel de couts et de capacites, saisissez la demande "
    "du scenario 1, puis definissez les variations du scenario 2."
)

cost_file = st.file_uploader(
    "Fichier Excel des couts",
    type=["xlsx", "xls"],
)
capacity_file = st.file_uploader(
    "Fichier Excel des capacites",
    type=["xlsx", "xls"],
)

if cost_file is None or capacity_file is None:
    st.info("Chargez les deux fichiers Excel pour commencer.")
    st.stop()

try:
    sites, regions, variable_costs, fixed_costs, cost_df = read_cost_file(cost_file)
    capacities, capacity_df = read_capacity_file(capacity_file)
except Exception as exc:
    st.error(str(exc))
    st.stop()

st.subheader("Donnees chargees")
left_column, right_column = st.columns(2)

with left_column:
    st.write("Couts variables")
    st.dataframe(cost_df, use_container_width=True)

with right_column:
    st.write("Capacites")
    st.dataframe(capacity_df, use_container_width=True)

st.subheader("Demandes par region")
scenario_columns = st.columns(2)
scenario_1_demands = {}
scenario_2_demands = {}
scenario_2_variations = {}

with scenario_columns[0]:
    st.write("Scenario 1 - Demande")
    for region in regions:
        scenario_1_demands[region] = st.number_input(
            region,
            min_value=0.0,
            value=0.0,
            step=1.0,
            key=f"scenario_1_{region}",
        )

with scenario_columns[1]:
    st.write("Scenario 2 - Variation par rapport au scenario 1")
    for region in regions:
        scenario_2_variations[region] = st.number_input(
            f"{region} - variation (%)",
            min_value=-100.0,
            value=0.0,
            step=1.0,
            key=f"scenario_2_variation_{region}",
        )
        scenario_2_demands[region] = scenario_1_demands[region] * (
            1 + scenario_2_variations[region] / 100
        )

st.subheader("Indicateurs avant optimisation")
total_capacity = sum(capacities.get(site, 0) for site in sites)
total_demand_scenario_1 = sum(scenario_1_demands.values())
total_demand_scenario_2 = sum(scenario_2_demands.values())

metric_columns = st.columns(5)
metric_columns[0].metric("Capacite totale", f"{total_capacity:,.2f}")
metric_columns[1].metric("Demande totale Scenario 1", f"{total_demand_scenario_1:,.2f}")
metric_columns[2].metric("Demande totale Scenario 2", f"{total_demand_scenario_2:,.2f}")
metric_columns[3].metric(
    "Ecart capacite - demande S1",
    f"{total_capacity - total_demand_scenario_1:,.2f}",
)
metric_columns[4].metric(
    "Ecart capacite - demande S2",
    f"{total_capacity - total_demand_scenario_2:,.2f}",
)

st.write("Demande calculee du Scenario 2")
scenario_2_demand_df = pd.DataFrame(
    {
        "Region": regions,
        "Demande Scenario 1": [scenario_1_demands[region] for region in regions],
        "Variation Scenario 2": [scenario_2_variations[region] for region in regions],
        "Demande Scenario 2": [scenario_2_demands[region] for region in regions],
    }
)
st.dataframe(
    scenario_2_demand_df.style.format({"Variation Scenario 2": "{:.1f}%"}),
    use_container_width=True,
)

allow_closure = st.checkbox("Autoriser la fermeture des sites", value=True)

if st.button("Lancer l'optimisation"):
    errors = []
    errors.extend(validate_uploaded_data(
        sites,
        regions,
        variable_costs,
        capacities,
        scenario_1_demands,
        fixed_costs,
        "Scenario 1",
    ))
    errors.extend(validate_uploaded_data(
        sites,
        regions,
        variable_costs,
        capacities,
        scenario_2_demands,
        fixed_costs,
        "Scenario 2",
    ))

    if errors:
        for error in errors:
            st.error(error)
        st.stop()

    try:
        scenario_1_solution = solve_design_model(
            sites=sites,
            regions=regions,
            variable_costs=variable_costs,
            fixed_costs=fixed_costs,
            capacities=capacities,
            demands=scenario_1_demands,
            allow_closure=allow_closure,
        )
        scenario_2_solution = solve_design_model(
            sites=sites,
            regions=regions,
            variable_costs=variable_costs,
            fixed_costs=fixed_costs,
            capacities=capacities,
            demands=scenario_2_demands,
            allow_closure=allow_closure,
        )
    except Exception as exc:
        st.error(str(exc))
        st.stop()

    display_solution("Resultats Scenario 1", sites, regions, scenario_1_solution)
    display_solution("Resultats Scenario 2", sites, regions, scenario_2_solution)

    st.subheader("Tableau de comparaison synthetique")
    comparison_df = build_comparison_dataframe(
        scenario_1_solution,
        scenario_2_solution,
        sites,
    )
    st.dataframe(comparison_df, use_container_width=True)

    if scenario_1_solution["has_solution"] and scenario_2_solution["has_solution"]:
        st.write("Comparaison des capacites par site")
        site_comparison_df = build_site_comparison_dataframe(
            sites,
            scenario_1_solution,
            scenario_2_solution,
        )
        st.dataframe(
            site_comparison_df.style.format({
                "Taux utilisation S1": "{:.1%}",
                "Taux utilisation S2": "{:.1%}",
            }),
            use_container_width=True,
        )

    st.subheader("Matrices des flux")
    st.write("Matrice des flux - Scenario 1")
    st.dataframe(
        build_flow_dataframe(sites, regions, scenario_1_solution),
        use_container_width=True,
    )

    st.write("Matrice des flux - Scenario 2")
    st.dataframe(
        build_flow_dataframe(sites, regions, scenario_2_solution),
        use_container_width=True,
    )
