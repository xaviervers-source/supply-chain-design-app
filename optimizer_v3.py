from ortools.linear_solver import pywraplp


def validate_model_data(
    sites,
    regions,
    variable_costs,
    fixed_costs,
    capacities,
    demands,
    allow_closure,
):
    """Retourne la liste des erreurs detectees dans les donnees du modele."""
    errors = []

    if not isinstance(allow_closure, bool):
        errors.append("allow_closure doit etre un booleen True ou False.")

    for site in sites:
        if site not in capacities:
            errors.append(f"Capacite manquante pour le site {site}.")
        elif capacities[site] <= 0:
            errors.append(f"La capacite du site {site} doit etre positive.")

        if site not in fixed_costs:
            errors.append(f"Cout fixe manquant pour le site {site}.")
        elif fixed_costs[site] < 0:
            errors.append(f"Le cout fixe du site {site} ne peut pas etre negatif.")

    for region in regions:
        if region not in demands:
            errors.append(f"Demande manquante pour la region {region}.")
        elif demands[region] < 0:
            errors.append(f"La demande de la region {region} ne peut pas etre negative.")

    for site in sites:
        for region in regions:
            if (site, region) not in variable_costs:
                errors.append(f"Cout variable manquant pour {site} -> {region}.")
            elif variable_costs[site, region] < 0:
                errors.append(f"Cout variable negatif pour {site} -> {region}.")

    total_capacity = sum(capacities.get(site, 0) for site in sites)
    total_demand = sum(demands.get(region, 0) for region in regions)
    if total_capacity < total_demand:
        errors.append(
            "Capacite totale insuffisante : "
            f"{total_capacity:,.0f} disponible pour {total_demand:,.0f} demande."
        )

    return errors


def solve_design_model(
    sites,
    regions,
    variable_costs,
    fixed_costs,
    capacities,
    demands,
    allow_closure,
):
    """
    Resout le modele de Supply Chain Design.

    Variables :
    - X[i,j] >= 0 : quantite envoyee du site i vers la region j
    - Y[i] binaire : 1 si le site i est ouvert, 0 sinon
    """
    errors = validate_model_data(
        sites,
        regions,
        variable_costs,
        fixed_costs,
        capacities,
        demands,
        allow_closure,
    )
    if errors:
        raise ValueError("\n".join(errors))

    solver = pywraplp.Solver.CreateSolver("SCIP")
    if solver is None:
        raise RuntimeError("Le solveur SCIP n'est pas disponible dans OR-Tools.")

    infinity = solver.infinity()

    # X[i,j] : flux du site i vers la region j.
    flows = {}
    for site in sites:
        for region in regions:
            flows[site, region] = solver.NumVar(
                0,
                infinity,
                f"X_{site}_{region}",
            )

    # Y[i] : variable d'ouverture du site i.
    site_is_open = {}
    for site in sites:
        site_is_open[site] = solver.BoolVar(f"Y_{site}")

    # Chaque region doit recevoir exactement sa demande.
    for region in regions:
        solver.Add(
            sum(flows[site, region] for site in sites) == demands[region],
            f"Demand_{region}",
        )

    # Chaque site respecte sa capacite seulement s'il est ouvert.
    for site in sites:
        solver.Add(
            sum(flows[site, region] for region in regions)
            <= capacities[site] * site_is_open[site],
            f"Capacity_{site}",
        )

    # Si la fermeture n'est pas autorisee, tous les sites sont forces ouverts.
    if not allow_closure:
        for site in sites:
            solver.Add(site_is_open[site] == 1, f"Force_open_{site}")

    variable_cost_expression = sum(
        variable_costs[site, region] * flows[site, region]
        for site in sites
        for region in regions
    )
    fixed_cost_expression = sum(
        fixed_costs[site] * site_is_open[site]
        for site in sites
    )
    solver.Minimize(variable_cost_expression + fixed_cost_expression)

    status = solver.Solve()
    status_names = {
        pywraplp.Solver.OPTIMAL: "OPTIMAL",
        pywraplp.Solver.FEASIBLE: "FEASIBLE",
        pywraplp.Solver.INFEASIBLE: "INFEASIBLE",
        pywraplp.Solver.UNBOUNDED: "UNBOUNDED",
        pywraplp.Solver.ABNORMAL: "ABNORMAL",
        pywraplp.Solver.NOT_SOLVED: "NOT_SOLVED",
    }

    if status not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
        return {
            "status": status,
            "status_name": status_names.get(status, str(status)),
            "has_solution": False,
        }

    flow_values = {}
    site_status = {}
    site_summary = {}

    for site in sites:
        site_status[site] = "ouvert" if site_is_open[site].solution_value() > 0.5 else "ferme"
        total_site = 0

        for region in regions:
            value = flows[site, region].solution_value()
            if abs(value) < 1e-7:
                value = 0
            flow_values[site, region] = value
            total_site += value

        remaining_capacity = capacities[site] - total_site
        utilization_rate = total_site / capacities[site] if capacities[site] else 0

        site_summary[site] = {
            "capacite": capacities[site],
            "volume": total_site,
            "taux_utilisation": utilization_rate,
            "capacite_restante": remaining_capacity,
        }

    variable_cost_value = sum(
        variable_costs[site, region] * flow_values[site, region]
        for site in sites
        for region in regions
    )
    fixed_cost_value = sum(
        fixed_costs[site] * site_is_open[site].solution_value()
        for site in sites
    )

    return {
        "status": status,
        "status_name": status_names.get(status, str(status)),
        "has_solution": True,
        "total_cost": solver.Objective().Value(),
        "variable_cost": variable_cost_value,
        "fixed_cost": fixed_cost_value,
        "site_status": site_status,
        "flows": flow_values,
        "site_summary": site_summary,
    }


def extract_kpis(solution, sites):
    """
    Extrait les indicateurs principaux d'une solution.

    Cette fonction ne modifie pas le modele mathematique. Elle sert seulement
    a preparer les tableaux de comparaison entre scenarios.
    """
    if not solution.get("has_solution"):
        return {
            "statut": solution["status_name"],
            "cout_total": None,
            "cout_variable": None,
            "cout_fixe": None,
            "nombre_sites_ouverts": None,
            "sites_ouverts": "",
        }

    open_sites = [
        site
        for site in sites
        if solution["site_status"][site] == "ouvert"
    ]

    return {
        "statut": solution["status_name"],
        "cout_total": solution["total_cost"],
        "cout_variable": solution["variable_cost"],
        "cout_fixe": solution["fixed_cost"],
        "nombre_sites_ouverts": len(open_sites),
        "sites_ouverts": ", ".join(open_sites),
    }
