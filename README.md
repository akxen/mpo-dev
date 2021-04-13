# Multi-period Porfolio Optimisation API
This repository implements a version of the multi-period portfolio optimisation algorithm presented in:

Boyd, S., Busseti, E., Diamond, S., Kahn, R. N., Koh, K., Nystrup, P., & Speth, J. (2017). Multi-period trading via convex optimization. arXiv preprint arXiv:1705.00109.

Link: https://stanford.edu/~boyd/papers/pdf/cvx_portfolio.pdf

Pyomo is used to formulate the optimisation problem while GLPK is used as the solver. Users interact with the model via an API which has been created using the Django REST Framework. This approach decouples the technology used to formulate and solve the model from the method by which data is submitted to the model. Any tool or programming language capable of submitting POST requests can be used to interact with the model via the API.

The model used by the API can be found in [project/api/optimisation/model.py](project/api/optimisation/model.py).

## Quickstart
Setup the configuration file by following instructions in [config/secret-template.env](config/secret-template.env)


Run docker-compose to start the container:

```
docker-compose -f docker-compose.yml up --build
```

Prepare model data:

```
{
    "initial_weights": {
        "GOOG": 0,
        "APPL": 0,
        "CASH": 1
    },
    "estimated_returns": {
        "GOOG": {
            "1": 0.05,
            "2": 0.02,
            "3": -0.1
        },
        "APPL": {
            "1": 0.04,
            "2": 0.01,
            "3": -0.03
        }
    },
    "parameters": {
        "min_weight": -1,
        "max_weight": 0.1,
        "min_cash_balance": 0.1,
        "max_leverage": 1,
        "max_trade_size": 0.1,
        "trade_aversion": 1,
        "transaction_cost": 0.01
    }
}
```

Submit a POST request using model data as the request body to the following endpoint:

```
http://localhost:8000/api/run
```

Example:

```
curl --header "Content-Type: application/json" \
--request POST \
--data '{"initial_weights": {
            "GOOG": 0,
            "APPL": 0,
            "CASH": 1
            },
        "estimated_returns": {
            "GOOG": {
                "1": 0.05,
                "2": 0.02,
                "3": -0.1
            },
            "APPL": {
                "1": 0.04,
                "2": 0.01,
                "3": -0.03
            }
        },
        "parameters": {
            "min_weight": -1,
            "max_weight": 0.1,
            "min_cash_balance": 0.1,
            "max_leverage": 1,
            "max_trade_size": 0.1,
            "trade_aversion": 1,
            "transaction_cost": 0.01
        }
}' \
http://localhost:8000/api/run
```

This produces the following output:

```
{
    "output": {
        "weights": {
            "GOOG": {
                "1": 0,
                "2": 0.2,
                "3": 0.2,
                "4": 0
            },
            "APPL": {
                "1": 0,
                "2": 0.2,
                "3": 0.2,
                "4": 0
            },
            "CASH": {
                "1": 1,
                "2": 0.6,
                "3": 0.6,
                "4": 1
            }
        },
        "trades": {
            "GOOG": {
                "1": 0.2,
                "2": 0,
                "3": -0.2
            },
            "APPL": {
                "1": 0.2,
                "2": 0,
                "3": -0.2
            },
            "CASH": {
                "1": -0.4,
                "2": 0,
                "3": 0.4
            }
        }
    },
    "status": 0
}
```

The model computes normalised portfolio weights that should be observed at the start of each period, along with normalised trades that realise these weights. Weights in the first period are fixed to values contained within `"initial_weights"`. A terminal constraint enforces non-cash assets be liquidated in the final period.

The optimisation problem seeks to identify the plan of investment decisions that maximises the portfolio's value over the investment horizon. Only the first step in the plan would be implemented in practice, with the procedure repeated at the start of each interval using updated forecasts. This pattern of periodically developing a plan but only implementing the first step falls within the paradigm of model predictive control, also known as receding horizon control.

## Model data

### Initial weights
A cash account (denoted `"CASH"`) must always be included within the `"initial_weights"` object. Initial weights for each asset must sum to 1.

```
"initial_weights": {
    "GOOG": 0,
    "APPL": 0,
    "CASH": 1
}
```

### Asset return forecasts
Forecast returns for each period over the model horizon must be provided for each asset. If three periods are specified then following should be submitted:

```
"estimated_returns": {
    "GOOG": {
        "1": 0.05,
        "2": 0.02,
        "3": -0.1
    },
    "APPL": {
        "1": 0.04,
        "2": 0.01,
        "3": -0.03
    }
```

If the model horizon is to consist of four periods then an additional forecast is required for each asset:

```
"estimated_returns": {
    "GOOG": {
        "1": 0.05,
        "2": 0.02,
        "3": -0.1
        "4": 0.01
    },
    "APPL": {
        "1": 0.04,
        "2": 0.01,
        "3": -0.03
        "4": -0.01
    }
```

All assets should specify the same number of forecast periods.

### Adding assets
The `"initial_weights"` and `"estimated_returns"` objects must be updated when adding assets. For instance, consider adding AMZN. First update the `"initial weights"` object:

```
"initial_weights": {
    "AMZN": 0,
    "GOOG": 0,
    "APPL": 0,
    "CASH": 1
}
```
then include an object for the asset's estimated returns over the model horizon:

```
"estimated_returns": {
    "AMZN": {
        "1": 0.01,
        "2": 0.04,
        "3": -0.05
        "4": 0.03
    },
    ...
}
```


### Parameters
The following parameters impact the model's formulation:

| Parameter | Description | Default |
| --------- | ----------- | ------- |
| min_weight | Minimum weight non-cash asset can take in portfolio | -1 |
| max_weight | Maximum weight non-cash asset can take in portfolio | 1 |
| min_cash_balance | Minimum cash balance | 0 |
| max_leverage | Max leverage for portfolio | 1 |
| max_trade_size | Max trade size as a proportion of the portfolio's total value | 1 |
| trade_aversion | Hyperparameter used to linearly scale trade cost - increasing value dissuades trading | 1 |
| trade_cost | Trade cost a proportion of trade value e.g. 0.01 = 1% of trade value | 0.01 |

Defaults can be overridden by specifying these parameters in the request body as shown in the example above.

## Solution status
A code is returned to indicate if the model was solved to optimality. The following `"status"` codes may be observed:

| Status code | Description |
| ----------- | ----------- |
| 0 | Optimal solution obtained |
| 1 | Model is infeasible or suboptimal solution returned |

## Caveats
1. THIS MODEL IS NOT INTENDED FOR USE IN PRODUCTION.

2. This is not a full implementation of the model described in the reference listed above. For example, risk measures are not included in the objective and holding costs are omitted. A simplified transaction cost model has also been used. The model in [project/api/optimisation/model.py](project/api/optimisation/model.py) can be extended to suit different use cases and requirements.

3. Djano is configured for local development (i.e. `manage.py runserver` is used, and `DEBUG=True`).