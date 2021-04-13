"""
Construct, solve, and extract results from a multi-period portfolio
optimisation model. The model follows the formulation described in:

Boyd, S., Busseti, E., Diamond, S., Kahn, R. N., Koh, K., Nystrup, P.,
& Speth, J. (2017). Multi-period trading via convex optimization. arXiv
preprint arXiv:1705.00109.

Link: https://stanford.edu/~boyd/papers/pdf/cvx_portfolio.pdf

Note: to assist with the identification of model components within expressions
and constraints the following prefixes are assigned:
    S - set
    P - parameter
    V - variable
    E - expression
    C - constraint
"""

import pyomo.environ as pyo
from pyomo.opt import SolverStatus, TerminationCondition

# Required if running within web app
# See: https://github.com/PyUtilib/pyutilib/issues/31#issuecomment-382479024
import pyutilib.subprocess.GlobalData
pyutilib.subprocess.GlobalData.DEFINE_SIGNAL_HANDLERS_DEFAULT = False


def define_sets(m, data):
    """Define sets for variables, parameters, expression, and constraints"""

    # Universe of assets
    m.S_ASSETS = pyo.Set(initialize=data['S_ASSETS'])

    # Trading periods
    m.S_PERIODS = pyo.Set(initialize=data['S_PERIODS'], ordered=True)

    # Denotes point in time at start of each period
    # Note: len(S_PERIODS) = len(S_TIME_INDEX) - 1
    m.S_TIME_INDEX = pyo.Set(initialize=data['S_TIME_INDEX'], ordered=True)

    return m


def define_parameters(m, data):
    """Define model parameters"""

    # Min and max portfolio weights for a given asset
    m.P_MIN_WEIGHT = pyo.Param(initialize=data['P_MIN_WEIGHT'])
    m.P_MAX_WEIGHT = pyo.Param(initialize=data['P_MAX_WEIGHT'])

    # Min cash balance over horizon (normalised by portfolio value)
    m.P_MIN_CASH_BALANCE = pyo.Param(initialize=data['P_MIN_CASH_BALANCE'])

    # Max leverage and trade size
    m.P_MAX_LEVERAGE = pyo.Param(initialize=data['P_MAX_LEVERAGE'])
    m.P_MAX_TRADE_SIZE = pyo.Param(initialize=data['P_MAX_TRADE_SIZE'])

    # Transaction cost as percentage of trade value
    m.P_TRANSACTION_COST = pyo.Param(initialize=data['P_TRANSACTION_COST'])

    # Hyper parameter that disincentivises trading when increased
    m.P_TRADE_AVERSION = pyo.Param(initialize=data['P_TRADE_AVERSION'])

    # Initial portfolio weights for each asset
    m.P_INITIAL_WEIGHT = pyo.Param(m.S_ASSETS, initialize=data['P_INITIAL_WEIGHT'])

    # Estimated returns for each asset
    m.P_RETURN = pyo.Param(m.S_ASSETS, m.S_PERIODS, initialize=data['P_RETURN'])

    return m


def define_variables(m):
    """Define model variables"""

    # Portfolio weight for each asset and time period
    m.V_WEIGHT = pyo.Var(m.S_ASSETS, m.S_TIME_INDEX)

    # Normalised trade amount for each asset and time period
    m.V_TRADE = pyo.Var(m.S_ASSETS, m.S_PERIODS)

    # Dummy variables used to compute absolute normalised trade value - used
    # when computing transaction costs
    m.V_TRADE_DUMMY_1 = pyo.Var(m.S_ASSETS, m.S_PERIODS, within=pyo.NonNegativeReals)
    m.V_TRADE_DUMMY_2 = pyo.Var(m.S_ASSETS, m.S_PERIODS, within=pyo.NonNegativeReals)

    # Dummy variables used to compute absolute value for post-trade weights -
    # used in max leverage constraint
    m.V_POST_TRADE_WEIGHT_DUMMY_1 = pyo.Var(
        m.S_ASSETS, m.S_TIME_INDEX, within=pyo.NonNegativeReals)
    m.V_POST_TRADE_WEIGHT_DUMMY_2 = pyo.Var(
        m.S_ASSETS, m.S_TIME_INDEX, within=pyo.NonNegativeReals)

    return m


def define_expressions(m):
    """Define model expressions"""

    def abs_trade_rule(m, a, t):
        """Absolute value for normalised trade amount"""

        return m.V_TRADE_DUMMY_1[a, t] + m.V_TRADE_DUMMY_2[a, t]

    m.E_ABS_TRADE = pyo.Expression(m.S_ASSETS, m.S_PERIODS, rule=abs_trade_rule)

    def abs_post_trade_weight_rule(m, a, t):
        """Absolute value for new weights after making trades"""

        return m.V_POST_TRADE_WEIGHT_DUMMY_1[a, t] + m.V_POST_TRADE_WEIGHT_DUMMY_2[a, t]

    m.E_ABS_POST_TRADE_WEIGHT = pyo.Expression(
        m.S_ASSETS, m.S_PERIODS, rule=abs_post_trade_weight_rule)

    return m


def define_constraints(m):
    """Define model constraints"""

    def transition_rule(m, a, t):
        """Transition function connecting weights and trades across periods"""

        return m.V_WEIGHT[a, t + 1] == m.V_WEIGHT[a, t] + m.V_TRADE[a, t]

    m.C_TRANSITION = pyo.Constraint(m.S_ASSETS, m.S_PERIODS, rule=transition_rule)

    def self_financing_rule(m, t):
        """Simplified self-financing rule - enforces trade balance"""

        return sum(m.V_TRADE[a, t] for a in m.S_ASSETS) == 0

    m.C_SELF_FINANCING = pyo.Constraint(m.S_PERIODS, rule=self_financing_rule)

    def terminal_weight_rule(m, a):
        """All assets in cash for final period"""

        if a == 'CASH':
            return m.V_WEIGHT[a, m.S_TIME_INDEX.last()] == 1
        else:
            return m.V_WEIGHT[a, m.S_TIME_INDEX.last()] == 0

    m.C_TERMINAL_WEIGHT = pyo.Constraint(m.S_ASSETS, rule=terminal_weight_rule)

    def min_weight_rule(m, a, t):
        """Lower bound for non-cash asset weights within portfolio"""

        if a == 'CASH':
            return pyo.Constraint.Skip

        return m.V_WEIGHT[a, t] + m.V_TRADE[a, t] >= m.P_MIN_WEIGHT

    m.C_MIN_WEIGHT = pyo.Constraint(m.S_ASSETS, m.S_PERIODS, rule=min_weight_rule)

    def max_weight_rule(m, a, t):
        """Upper bound for non-cash asset weights within portfolio"""

        if a == 'CASH':
            return pyo.Constraint.Skip

        return m.V_WEIGHT[a, t] + m.V_TRADE[a, t] <= m.P_MAX_WEIGHT

    m.C_MAX_WEIGHT = pyo.Constraint(m.S_ASSETS, m.S_PERIODS, rule=max_weight_rule)

    def min_cash_balance_rule(m, t):
        """Minimum weight assigned to cash"""

        return m.V_WEIGHT['CASH', t] + m.V_TRADE['CASH', t] >= m.P_MIN_CASH_BALANCE

    m.C_MIN_CASH_BALANCE = pyo.Constraint(m.S_PERIODS, rule=min_cash_balance_rule)

    def long_only_rule(m, a, t):
        """Prevent shorting of assets"""

        return m.V_WEIGHT[a, t] + m.V_TRADE[a, t] >= 0

    m.C_LONG_ONLY = pyo.Constraint(m.S_ASSETS, m.S_PERIODS, rule=long_only_rule)

    def max_leverage_rule(m, t):
        """Max leverage for portfolio"""

        return (sum(m.E_ABS_POST_TRADE_WEIGHT[a, t] for a in m.S_ASSETS if a != 'CASH')
                <= m.P_MAX_LEVERAGE)

    m.C_MAX_LEVERAGE = pyo.Constraint(m.S_PERIODS, rule=max_leverage_rule)

    def max_trade_size_rule(m, a, t):
        """Max trade size"""

        if a != 'CASH':
            return m.E_ABS_TRADE[a, t] <= m.P_MAX_TRADE_SIZE

        return pyo.Constraint.Skip

    m.C_MAX_TRADE_SIZE = pyo.Constraint(m.S_ASSETS, m.S_PERIODS, rule=max_trade_size_rule)

    def initial_weights_rule(m, a):
        """Fix weights at start of first period"""

        return m.V_WEIGHT[a, 1] == m.P_INITIAL_WEIGHT[a]

    m.C_INITIAL_WEIGHT = pyo.Constraint(m.S_ASSETS, rule=initial_weights_rule)

    # Constraints used to compute absolute trade value
    def abs_trade_1_rule(m, a, t):
        return m.V_TRADE_DUMMY_1[a, t] >= m.V_TRADE[a, t]

    m.C_ABS_TRADE_1 = pyo.Constraint(m.S_ASSETS, m.S_PERIODS, rule=abs_trade_1_rule)

    def abs_trade_2_rule(m, a, t):
        return m.V_TRADE_DUMMY_2[a, t] >= -m.V_TRADE[a, t]

    m.C_ABS_TRADE_2 = pyo.Constraint(m.S_ASSETS, m.S_PERIODS, rule=abs_trade_2_rule)

    # Constraints used to compute absolute values for post-trade weights
    def abs_post_trade_weight_1_rule(m, a, t):
        return m.V_POST_TRADE_WEIGHT_DUMMY_1[a, t] >= m.V_TRADE[a, t] + m.V_WEIGHT[a, t]

    m.C_ABS_POST_TRADE_WEIGHT_1 = pyo.Constraint(
        m.S_ASSETS, m.S_PERIODS, rule=abs_post_trade_weight_1_rule)

    def abs_post_trade_weight_2_rule(m, a, t):
        return m.V_POST_TRADE_WEIGHT_DUMMY_2[a, t] >= - (m.V_TRADE[a, t] + m.V_WEIGHT[a, t])

    m.C_ABS_POST_TRADE_WEIGHT_2 = pyo.Constraint(
        m.S_ASSETS, m.S_PERIODS, rule=abs_post_trade_weight_2_rule)

    return m


def define_objective(m):
    """Define objective function"""

    def objective_rule(m):
        """
        Objective function maximises estimated returns taking into account
        trade costs. Risk measures can also be added to maximise the
        risk-adjusted rate of return.
        """

        estimated_return = sum(m.P_RETURN[a, t] * (m.V_WEIGHT[a, t] + m.V_TRADE[a, t])
                               for a in m.S_ASSETS if a != 'CASH'
                               for t in m.S_PERIODS)

        # Absolute trade amount
        abs_trade = sum(m.E_ABS_TRADE[a, t] for a in m.S_ASSETS for t in m.S_PERIODS)

        # Trade cost = trade aversion param x trade amount x trade amount
        trade_cost = m.P_TRADE_AVERSION * m.P_TRANSACTION_COST * abs_trade

        return estimated_return - trade_cost

    m.OBJECTIVE = pyo.Objective(rule=objective_rule, sense=pyo.maximize)

    return m


def construct_model(data):
    """
    Create concrete model with user data

    Parameters
    ----------
    data : dict
        Model parameters specified by user

    Returns
    -------
    m : Pyomo model
        Concrete model populated with user specified data
    """

    # Initialise model
    m = pyo.ConcreteModel()

    # Define model components
    m = define_sets(m=m, data=data)
    m = define_parameters(m=m, data=data)
    m = define_variables(m=m)
    m = define_expressions(m=m)
    m = define_constraints(m=m)
    m = define_objective(m=m)

    return m


def solve_model(m):
    """
    Solve model - results attached to model instance

    Parameters
    ----------
    m : Pyomo model instance
        Model instance containing user defined data

    Returns
    -------
    m : Pyomo model instance
        Solved model instance
    """

    opt = pyo.SolverFactory('glpk')
    solution_info = opt.solve(m)

    return m, solution_info


def get_solution_status(solution_info):
    """Extract solver status and termination condition"""

    is_ok = solution_info.solver.status == SolverStatus.ok
    is_optimal = solution_info.solver.termination_condition == TerminationCondition.optimal

    # Return status code 0 for optimal solution, 1 for infeasible / suboptimal solution
    if is_ok and is_optimal:
        return 0
    else:
        return 1


def get_results(m, solution_info):
    """
    Extract model results as dict

    Parameters
    ----------
    m : Pyomo model instance
        Model instance containing solution (post-solve)

    Returns
    -------
    results : dict
        Dictionary containing model results
    """

    weights = {k: {str(i): m.V_WEIGHT[k, i].value for i in m.S_TIME_INDEX}
               for k in m.S_ASSETS}

    trades = {k: {str(i): m.V_TRADE[k, i].value for i in m.S_PERIODS}
              for k in m.S_ASSETS}

    results = {
        "output": {
            "weights": weights,
            "trades": trades
        },
        "status": get_solution_status(solution_info=solution_info)
    }

    return results


def process_inputs(data):
    """
    Process user inputs and apply default values if parameters not specified.

    Parameters
    ----------
    data : dict
        User input containing model parameters

    Returns
    -------
    out : dict
        Model data in format that allows construction of the Pyomo model
    """

    # Extract symbols for assets
    assets = list(data['initial_weights'].keys())

    # Number of intervals over multi-period optimisation horizon
    periods = [len(v.keys()) for k, v in data['estimated_returns'].items()][0]

    # Estimated return for each interval
    estimated_returns = {
        (i, int(k)): v for i, j in data['estimated_returns'].items() for k, v in j.items()
    }

    # Extract model parameters
    parameters = data.get('parameters', {})

    data = {
        'S_ASSETS': assets,
        'S_PERIODS': range(1, periods + 1),
        'S_TIME_INDEX': range(1, periods + 2),
        'P_RETURN': estimated_returns,
        'P_INITIAL_WEIGHT': data['initial_weights'],
        'P_MIN_WEIGHT': parameters.get('min_weight', -1),
        'P_MAX_WEIGHT': parameters.get('max_weight', 1),
        'P_MIN_CASH_BALANCE': parameters.get('min_cash_balance', 0),
        'P_MAX_LEVERAGE': parameters.get('max_leverage', 1),
        'P_MAX_TRADE_SIZE': parameters.get('max_trade_size', 1),
        'P_TRADE_AVERSION': parameters.get('trade_aversion', 1),
        'P_TRANSACTION_COST': parameters.get('transaction_cost', 0.001),
    }

    return data


def run_model(data):
    """
    Construct model, solve model, and extract results

    Parameters
    ----------
    data : dict
        User defined parameters for model instance

    Returns
    -------
    results : dict
        Model results
    """

    # Process user inputs so they can be used to construct the MPO model
    model_data = process_inputs(data=data)

    # Construct and solve model then extract results
    m = construct_model(data=model_data)
    m, solution_info = solve_model(m=m)
    results = get_results(m=m, solution_info=solution_info)

    return results
