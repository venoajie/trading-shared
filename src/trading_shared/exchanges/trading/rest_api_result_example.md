{
  "method": "private/pme/simulate",
  "params": {
    "currency": "ETH",
    "add_positions": true,
    "simulated_positions": {
      "ETH-PERPETUAL": -1
    }
  },
  "jsonrpc": "2.0",
  "id": 2
}

access-control-allow-headers: Authorization,User-Agent,Range,X-Requested-With,Content-Type,Partner
access-control-allow-methods: GET, POST, OPTIONS
access-control-allow-origin: https://www.deribit.com
cache-control: no-store
cf-cache-status: DYNAMIC
cf-ray: 9ce888c35bafce2e-SIN
content-encoding: gzip
content-length: 960
content-type: application/json
date: Sun, 15 Feb 2026 23:20:09 GMT
server: cloudflare
strict-transport-security: max-age=15768000
vary: Origin,Authorization,Partner, accept-encoding
x-frame-options: SAMEORIGIN
--------------------------------------------------------------------------------
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "ticker": {
      "ETH-PERPETUAL": {
        "index_price": 1949.34,
        "mark_price": 1949.49
      }
    },
    "index_price": {
      "eth_usd": 1949.34
    },
    "portfolio": {
      "position": {
        "ETH-PERPETUAL": -0.999487053
      },
      "currency": {}
    },
    "margins": {
      "eth": {
        "maintenance_margin": 0.125969249812,
        "initial_margin": 0.157461562,
        "initial_margin_details": {
          "open_orders_margin": 0,
          "mmp_margin": 0,
          "spot_margin": 0,
          "risk_matrix_margin": 0.157461562265,
          "risk_matrix_margin_details": {
            "correlation_contingency": 0,
            "worst_case": 0.15246412672881357,
            "worst_case_bucket": {
              "index": 25,
              "source": "standard",
              "bucket": 9,
              "side": "right"
            },
            "roll_shock": 0.004997435265,
            "delta_shock": 0
          }
        }
      }
    },
    "initial_risk_vectors": {
      "ETH-PERPETUAL": {
        "extended": [
          0.21939959699999997,
          0.21939959699999997,
          -0.15246412672881357,
          -0.15246412672881357,
          -0.15246412672881357,
          -0.15246412672881357,
          -0.15246412672881357,
          -0.15246412672881357
        ],
        "standard": [
          0.21939959699999997,
          0.21939959699999997,
          0.21939959699999997,
          0.155989308849711,
          0.155989308849711,
          0.155989308849711,
          0.09885036787912087,
          0.09885036787912087,
          0.09885036787912087,
          0.04709624857068063,
          0.04709624857068063,
          0.04709624857068063,
          0,
          0,
          0,
          -0.04304011233014354,
          -0.04304011233014354,
          -0.04304011233014354,
          -0.08252645391743119,
          -0.08252645391743119,
          -0.08252645391743119,
          -0.11888171996035243,
          -0.11888171996035243,
          -0.11888171996035243,
          -0.15246412672881357,
          -0.15246412672881357,
          -0.15246412672881357
        ]
      }
    },
    "aggregated_risk_vectors": {
      "eth_eth": {
        "extended": [
          0,
          0,
          0,
          0,
          0,
          0,
          0,
          0
        ],
        "standard": [
          0.13163975819999998,
          0.13163975819999998,
          0.13163975819999998,
          0.09359358530982659,
          0.09359358530982659,
          0.09359358530982659,
          0.05931022072747252,
          0.05931022072747252,
          0.05931022072747252,
          0.028257749142408375,
          0.028257749142408375,
          0.028257749142408375,
          0,
          0,
          0,
          -0.04304011233014354,
          -0.04304011233014354,
          -0.04304011233014354,
          -0.08252645391743119,
          -0.08252645391743119,
          -0.08252645391743119,
          -0.11888171996035243,
          -0.11888171996035243,
          -0.11888171996035243,
          -0.15246412672881357,
          -0.15246412672881357,
          -0.15246412672881357
        ]
      }
    },
    "model_params": {
      "general": {
        "timestamp": 1771197609587,
        "mm_factor": 0.8,
        "buckets_count": 4,
        "vol_scenarios_count": 3
      },
      "currency": {
        "eth": {
          "min_annualised_move": 0.005,
          "annualised_move_risk": 0.05,
          "pnl_offset": 0.6,
          "correlation_set": false,
          "equity_side_impact": "both",
          "haircut": 0,
          "extended_dampener": 200000,
          "max_offsetable_pnl": 20000000
        },
        "usd": {
          "min_annualised_move": 0.01,
          "annualised_move_risk": 0.1,
          "pnl_offset": 0.4,
          "correlation_set": false,
          "equity_side_impact": "none",
          "haircut": 0,
          "extended_dampener": 25000,
          "max_offsetable_pnl": 1000000
        }
      },
      "currency_pair": {
        "eth_usd": {
          "price_range": 0.18,
          "m_inc": 0.000004,
          "delta_total_liq_shock_threshold": 20000000,
          "max_delta_shock": 0.1,
          "min_volatility_for_shock_up": 0.5,
          "volatility_range_up": 0.4,
          "volatility_range_down": 0.25,
          "extended_table_factor": 1,
          "short_term_vega_power": 0.3,
          "long_term_vega_power": 0.13
        }
      }
    },
    "pre_aggregated_risk_vectors": {
      "eth_eth": {
        "extended": [
          0.21939959699999997,
          0.21939959699999997,
          -0.15246412672881357,
          -0.15246412672881357,
          -0.15246412672881357,
          -0.15246412672881357,
          -0.15246412672881357,
          -0.15246412672881357
        ],
        "standard": [
          0.21939959699999997,
          0.21939959699999997,
          0.21939959699999997,
          0.155989308849711,
          0.155989308849711,
          0.155989308849711,
          0.09885036787912087,
          0.09885036787912087,
          0.09885036787912087,
          0.04709624857068063,
          0.04709624857068063,
          0.04709624857068063,
          0,
          0,
          0,
          -0.04304011233014354,
          -0.04304011233014354,
          -0.04304011233014354,
          -0.08252645391743119,
          -0.08252645391743119,
          -0.08252645391743119,
          -0.11888171996035243,
          -0.11888171996035243,
          -0.11888171996035243,
          -0.15246412672881357,
          -0.15246412672881357,
          -0.15246412672881357
        ]
      }
    }
  },
  "usIn": 1771197609585683,
  "usOut": 1771197609588021,
  "usDiff": 2338,
  "testnet": false
}


{
  "method": "private/simulate_portfolio",
  "params": {
    "currency": "ETH",
    "add_positions": true,
    "simulated_positions": {
      "ETH-PERPETUAL": -1
    }
  },
  "jsonrpc": "2.0",
  "id": 1
}

access-control-allow-headers: Authorization,User-Agent,Range,X-Requested-With,Content-Type,Partner
access-control-allow-methods: GET, POST, OPTIONS
access-control-allow-origin: https://www.deribit.com
cache-control: no-store
cf-cache-status: DYNAMIC
cf-ray: 9ce8868d8c3040fd-SIN
content-encoding: gzip
content-length: 511
content-type: application/json
date: Sun, 15 Feb 2026 23:18:39 GMT
server: cloudflare
strict-transport-security: max-age=15768000
vary: Origin,Authorization,Partner, accept-encoding
x-frame-options: SAMEORIGIN
--------------------------------------------------------------------------------
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "options_value": 0,
    "locked_balance": 0,
    "total_maintenance_margin_usd": 0.5951478760000001,
    "options_vega_map": {},
    "futures_session_upl": 0,
    "portfolio_margining_enabled": true,
    "total_delta_total_usd": -1.95422,
    "session_rpl": -0.000034,
    "options_gamma": 0,
    "options_session_upl": 0,
    "options_theta": 0,
    "margin_model": "cross_pm",
    "options_pl": 0,
    "initial_margin": 0.000417,
    "projected_maintenance_margin": 0.000305,
    "delta_total": 0,
    "maintenance_margin": 0.000305,
    "delta_total_map": {
      "eth_usd": 0
    },
    "total_initial_margin_usd": 0.814286765,
    "balance": 0.000031,
    "futures_session_rpl": -0.000034,
    "additional_reserve": 0,
    "cross_collateral_enabled": true,
    "options_vega": 0,
    "futures_pl": 0,
    "fee_balance": 0,
    "projected_delta_total": 0,
    "options_theta_map": {},
    "session_upl": 0,
    "options_delta": 0,
    "equity": -0.000002,
    "projected_initial_margin": 0.000417,
    "spot_reserve": 0,
    "total_equity_usd": 2.531603551,
    "total_pl": 0,
    "margin_balance": 0.001296,
    "currency": "ETH",
    "available_funds": 0.000879,
    "total_margin_balance_usd": 2.531603551,
    "options_session_rpl": 0,
    "available_withdrawal_funds": 0,
    "options_gamma_map": {}
  },
  "usIn": 1771197519070955,
  "usOut": 1771197519076417,
  "usDiff": 5462,
  "testnet": false
}

{
  "method": "private/get_account_summaries",
  "params": {
    "extended": true
  },
  "jsonrpc": "2.0",
  "id": 4
}
access-control-allow-headers: Authorization,User-Agent,Range,X-Requested-With,Content-Type,Partner
access-control-allow-methods: GET, POST, OPTIONS
access-control-allow-origin: https://www.deribit.com
cache-control: no-store
cf-cache-status: DYNAMIC
cf-ray: 9ce8936cbfdd9c21-SIN
content-encoding: gzip
content-length: 1845
content-type: application/json
date: Sun, 15 Feb 2026 23:27:26 GMT
server: cloudflare
strict-transport-security: max-age=15768000
vary: Origin,Authorization,Partner, accept-encoding
x-frame-options: SAMEORIGIN
--------------------------------------------------------------------------------
{
  "jsonrpc": "2.0",
  "id": 4,
  "result": {
    "id": 148510,
    "type": "subaccount",
    "mandatory_tfa": false,
    "mmp_enabled": false,
    "username": "MwaHaHa2020_1",
    "email": "ven.ajie@protonmail.com",
    "block_rfq_self_match_prevention": false,
    "creation_timestamp": 1607821349961,
    "login_enabled": false,
    "receive_notifications": false,
    "security_keys_enabled": true,
    "system_name": "MwaHaHa2020_1",
    "trading_products_details": [
      {
        "enabled": true,
        "product": "perpetual",
        "overwriteable": true,
        "requires_consent": false
      },
      {
        "enabled": true,
        "product": "futures",
        "overwriteable": true,
        "requires_consent": false
      },
      {
        "enabled": true,
        "product": "options",
        "overwriteable": true,
        "requires_consent": false
      },
      {
        "enabled": true,
        "product": "future_combos",
        "overwriteable": true,
        "requires_consent": false
      },
      {
        "enabled": true,
        "product": "option_combos",
        "overwriteable": true,
        "requires_consent": false
      },
      {
        "enabled": true,
        "product": "spots",
        "overwriteable": true,
        "requires_consent": false
      }
    ],
    "self_trading_extended_to_subaccounts": false,
    "change_margin_model_api_limit": {
      "timeframe": 86400000,
      "rate": 5
    },
    "summaries": [
      {
        "options_value": 0,
        "locked_balance": 0,
        "options_vega_map": {},
        "futures_session_upl": 0,
        "portfolio_margining_enabled": true,
        "session_rpl": 0,
        "options_gamma": 0,
        "options_session_upl": 0,
        "options_theta": 0,
        "margin_model": "segregated_pm",
        "options_pl": 0,
        "initial_margin": 0,
        "limits": {
          "matching_engine": {
            "block_rfq_maker": {
              "rate": 10,
              "burst": 20
            },
            "cancel_all": {
              "rate": 5,
              "burst": 20
            },
            "guaranteed_mass_quotes": {
              "rate": 2,
              "burst": 2
            },
            "maximum_mass_quotes": {
              "rate": 10,
              "burst": 10
            },
            "maximum_quotes": {
              "rate": 500,
              "burst": 500
            },
            "spot": {
              "rate": 5,
              "burst": 20
            },
            "trading": {
              "total": {
                "rate": 5,
                "burst": 20
              }
            }
          },
          "limits_per_currency": false,
          "non_matching_engine": {
            "rate": 20,
            "burst": 100
          }
        },
        "projected_maintenance_margin": 0,
        "delta_total": 0,
        "maintenance_margin": 0,
        "delta_total_map": {},
        "deposit_address": "0x93527d75ab49d44714822cab98e90423412fa2b8",
        "balance": 0,
        "futures_session_rpl": 0,
        "additional_reserve": 0,
        "cross_collateral_enabled": false,
        "options_vega": 0,
        "futures_pl": 0,
        "fee_balance": 0,
        "projected_delta_total": 0,
        "options_theta_map": {},
        "session_upl": 0,
        "options_delta": 0,
        "equity": 0,
        "projected_initial_margin": 0,
        "spot_reserve": 0,
        "total_pl": 0,
        "margin_balance": 0,
        "currency": "BNB",
        "available_funds": 0,
        "options_session_rpl": 0,
        "available_withdrawal_funds": 0,
        "options_gamma_map": {}
      },
      {
        "options_value": 0,
        "locked_balance": 0,
        "total_maintenance_margin_usd": 0.4557215915800001,
        "options_vega_map": {},
        "futures_session_upl": 0,
        "portfolio_margining_enabled": true,
        "total_delta_total_usd": -0.958299526,
        "session_rpl": 0,
        "options_gamma": 0,
        "options_session_upl": 0,
        "options_theta": 0,
        "margin_model": "cross_pm",
        "options_pl": 0,
        "initial_margin": 0.00000933,
        "limits": {
          "matching_engine": {
            "block_rfq_maker": {
              "rate": 10,
              "burst": 20
            },
            "cancel_all": {
              "rate": 5,
              "burst": 20
            },
            "guaranteed_mass_quotes": {
              "rate": 2,
              "burst": 2
            },
            "maximum_mass_quotes": {
              "rate": 10,
              "burst": 10
            },
            "maximum_quotes": {
              "rate": 500,
              "burst": 500
            },
            "spot": {
              "rate": 5,
              "burst": 20
            },
            "trading": {
              "total": {
                "rate": 5,
                "burst": 20
              }
            }
          },
          "limits_per_currency": false,
          "non_matching_engine": {
            "rate": 20,
            "burst": 100
          }
        },
        "projected_maintenance_margin": 0.00000664,
        "delta_total": 0,
        "maintenance_margin": 0.00000664,
        "delta_total_map": {},
        "deposit_address": "bc1qrnka8th77fvckku6gxskqtpfmp00kug2vcf9h6",
        "total_initial_margin_usd": 0.640151869,
        "balance": 0.0000348,
        "futures_session_rpl": 0,
        "additional_reserve": 0,
        "cross_collateral_enabled": true,
        "options_vega": 0,
        "futures_pl": 0,
        "fee_balance": 0,
        "projected_delta_total": 0,
        "options_theta_map": {},
        "session_upl": 0,
        "options_delta": 0,
        "equity": 0.0000348,
        "projected_initial_margin": 0.00000933,
        "spot_reserve": 0,
        "total_equity_usd": 2.531977059,
        "total_pl": 0,
        "margin_balance": 0.00003691,
        "currency": "BTC",
        "available_funds": 0.00002758,
        "total_margin_balance_usd": 2.531977059,
        "options_session_rpl": 0,
        "available_withdrawal_funds": 0,
        "options_gamma_map": {}
      },
      {
        "options_value": 0,
        "locked_balance": 0,
        "total_maintenance_margin_usd": 0.4557215915800001,
        "options_vega_map": {},
        "futures_session_upl": 0,
        "portfolio_margining_enabled": true,
        "total_delta_total_usd": -0.958299526,
        "session_rpl": 0,
        "options_gamma": 0,
        "options_session_upl": 0,
        "options_theta": 0,
        "margin_model": "cross_pm",
        "options_pl": 0,
        "initial_margin": 0.640152,
        "limits": {
          "matching_engine": {
            "block_rfq_maker": {
              "rate": 10,
              "burst": 20
            },
            "cancel_all": {
              "rate": 5,
              "burst": 20
            },
            "guaranteed_mass_quotes": {
              "rate": 2,
              "burst": 2
            },
            "maximum_mass_quotes": {
              "rate": 10,
              "burst": 10
            },
            "maximum_quotes": {
              "rate": 500,
              "burst": 500
            },
            "spot": {
              "rate": 5,
              "burst": 20
            },
            "trading": {
              "total": {
                "rate": 5,
                "burst": 20
              }
            }
          },
          "limits_per_currency": false,
          "non_matching_engine": {
            "rate": 20,
            "burst": 100
          }
        },
        "projected_maintenance_margin": 0.455722,
        "delta_total": 0,
        "maintenance_margin": 0.455722,
        "delta_total_map": {},
        "deposit_address": "0x93527d75ab49d44714822cab98e90423412fa2b8",
        "total_initial_margin_usd": 0.640151869,
        "balance": 0,
        "futures_session_rpl": 0,
        "additional_reserve": 0,
        "cross_collateral_enabled": true,
        "options_vega": 0,
        "futures_pl": 0,
        "fee_balance": 0,
        "projected_delta_total": 0,
        "options_theta_map": {},
        "session_upl": 0,
        "options_delta": 0,
        "equity": 0,
        "projected_initial_margin": 0.640152,
        "spot_reserve": 0,
        "total_equity_usd": 2.531977059,
        "total_pl": 0,
        "margin_balance": 2.531977,
        "currency": "BUIDL",
        "available_funds": 1.891825,
        "total_margin_balance_usd": 2.531977059,
        "options_session_rpl": 0,
        "available_withdrawal_funds": 0,
        "options_gamma_map": {}
      },
      {
        "options_value": 0,
        "locked_balance": 0,
        "total_maintenance_margin_usd": 0.4557215915800001,
        "options_vega_map": {},
        "futures_session_upl": -0.000033,
        "portfolio_margining_enabled": true,
        "total_delta_total_usd": -0.958299526,
        "session_rpl": 0,
        "options_gamma": 0,
        "options_session_upl": 0,
        "options_theta": 0,
        "margin_model": "cross_pm",
        "options_pl": 0,
        "initial_margin": 0.000327,
        "limits": {
          "matching_engine": {
            "block_rfq_maker": {
              "rate": 10,
              "burst": 20
            },
            "cancel_all": {
              "rate": 5,
              "burst": 20
            },
            "guaranteed_mass_quotes": {
              "rate": 2,
              "burst": 2
            },
            "maximum_mass_quotes": {
              "rate": 10,
              "burst": 10
            },
            "maximum_quotes": {
              "rate": 500,
              "burst": 500
            },
            "spot": {
              "rate": 5,
              "burst": 20
            },
            "trading": {
              "total": {
                "rate": 5,
                "burst": 20
              }
            }
          },
          "limits_per_currency": false,
          "non_matching_engine": {
            "rate": 20,
            "burst": 100
          }
        },
        "projected_maintenance_margin": 0.000233,
        "delta_total": 0.000511,
        "maintenance_margin": 0.000233,
        "delta_total_map": {
          "eth_usd": 0.00051096
        },
        "deposit_address": "0x93527d75ab49d44714822cab98e90423412fa2b8",
        "total_initial_margin_usd": 0.640151869,
        "balance": 0.000031,
        "futures_session_rpl": 0,
        "additional_reserve": 0,
        "cross_collateral_enabled": true,
        "options_vega": 0,
        "futures_pl": -0.000029,
        "fee_balance": 0,
        "projected_delta_total": 0.000511,
        "options_theta_map": {},
        "session_upl": -0.000033,
        "options_delta": 0,
        "equity": -0.000001,
        "projected_initial_margin": 0.000327,
        "spot_reserve": 0,
        "total_equity_usd": 2.531977059,
        "total_pl": -0.000029,
        "margin_balance": 0.001294,
        "currency": "ETH",
        "available_funds": 0.000967,
        "total_margin_balance_usd": 2.531977059,
        "options_session_rpl": 0,
        "available_withdrawal_funds": 0,
        "options_gamma_map": {}
      },
      {
        "options_value": 0,
        "locked_balance": 0,
        "options_vega_map": {},
        "futures_session_upl": 0,
        "portfolio_margining_enabled": false,
        "session_rpl": 0,
        "options_gamma": 0,
        "options_session_upl": 0,
        "options_theta": 0,
        "margin_model": "segregated_sm",
        "options_pl": 0,
        "initial_margin": 0,
        "limits": {
          "matching_engine": {
            "block_rfq_maker": {
              "rate": 10,
              "burst": 20
            },
            "cancel_all": {
              "rate": 5,
              "burst": 20
            },
            "guaranteed_mass_quotes": {
              "rate": 2,
              "burst": 2
            },
            "maximum_mass_quotes": {
              "rate": 10,
              "burst": 10
            },
            "maximum_quotes": {
              "rate": 500,
              "burst": 500
            },
            "spot": {
              "rate": 5,
              "burst": 20
            },
            "trading": {
              "total": {
                "rate": 5,
                "burst": 20
              }
            }
          },
          "limits_per_currency": false,
          "non_matching_engine": {
            "rate": 20,
            "burst": 100
          }
        },
        "projected_maintenance_margin": 0,
        "delta_total": 0,
        "maintenance_margin": 0,
        "delta_total_map": {},
        "balance": 0,
        "futures_session_rpl": 0,
        "additional_reserve": 0,
        "cross_collateral_enabled": false,
        "options_vega": 0,
        "futures_pl": 0,
        "fee_balance": 0,
        "projected_delta_total": 0,
        "options_theta_map": {},
        "session_upl": 0,
        "estimated_liquidation_ratio_map": {},
        "options_delta": 0,
        "equity": 0,
        "projected_initial_margin": 0,
        "spot_reserve": 0,
        "total_pl": 0,
        "margin_balance": 0,
        "currency": "ETHW",
        "estimated_liquidation_ratio": 0,
        "available_funds": 0,
        "options_session_rpl": 0,
        "available_withdrawal_funds": 0,
        "options_gamma_map": {}
      },
      {
        "options_value": 0,
        "locked_balance": 0,
        "options_vega_map": {},
        "futures_session_upl": 0,
        "portfolio_margining_enabled": true,
        "session_rpl": 0,
        "options_gamma": 0,
        "options_session_upl": 0,
        "options_theta": 0,
        "margin_model": "segregated_pm",
        "options_pl": 0,
        "initial_margin": 0,
        "limits": {
          "matching_engine": {
            "block_rfq_maker": {
              "rate": 10,
              "burst": 20
            },
            "cancel_all": {
              "rate": 5,
              "burst": 20
            },
            "guaranteed_mass_quotes": {
              "rate": 2,
              "burst": 2
            },
            "maximum_mass_quotes": {
              "rate": 10,
              "burst": 10
            },
            "maximum_quotes": {
              "rate": 500,
              "burst": 500
            },
            "spot": {
              "rate": 5,
              "burst": 20
            },
            "trading": {
              "total": {
                "rate": 5,
                "burst": 20
              }
            }
          },
          "limits_per_currency": false,
          "non_matching_engine": {
            "rate": 20,
            "burst": 100
          }
        },
        "projected_maintenance_margin": 0,
        "delta_total": 0,
        "maintenance_margin": 0,
        "delta_total_map": {},
        "deposit_address": "0x93527d75ab49d44714822cab98e90423412fa2b8",
        "balance": 0,
        "futures_session_rpl": 0,
        "additional_reserve": 0,
        "cross_collateral_enabled": false,
        "options_vega": 0,
        "futures_pl": 0,
        "fee_balance": 0,
        "projected_delta_total": 0,
        "options_theta_map": {},
        "session_upl": 0,
        "options_delta": 0,
        "equity": 0,
        "projected_initial_margin": 0,
        "spot_reserve": 0,
        "total_pl": 0,
        "margin_balance": 0,
        "currency": "EURR",
        "available_funds": 0,
        "options_session_rpl": 0,
        "available_withdrawal_funds": 0,
        "options_gamma_map": {}
      },
      {
        "options_value": 0,
        "locked_balance": 0,
        "options_vega_map": {},
        "futures_session_upl": 0,
        "portfolio_margining_enabled": true,
        "session_rpl": 0,
        "options_gamma": 0,
        "options_session_upl": 0,
        "options_theta": 0,
        "margin_model": "segregated_pm",
        "options_pl": 0,
        "initial_margin": 0,
        "limits": {
          "matching_engine": {
            "block_rfq_maker": {
              "rate": 10,
              "burst": 20
            },
            "cancel_all": {
              "rate": 5,
              "burst": 20
            },
            "guaranteed_mass_quotes": {
              "rate": 2,
              "burst": 2
            },
            "maximum_mass_quotes": {
              "rate": 10,
              "burst": 10
            },
            "maximum_quotes": {
              "rate": 500,
              "burst": 500
            },
            "spot": {
              "rate": 5,
              "burst": 20
            },
            "trading": {
              "total": {
                "rate": 5,
                "burst": 20
              }
            }
          },
          "limits_per_currency": false,
          "non_matching_engine": {
            "rate": 20,
            "burst": 100
          }
        },
        "projected_maintenance_margin": 0,
        "delta_total": 0,
        "maintenance_margin": 0,
        "delta_total_map": {},
        "deposit_address": "0x93527d75ab49d44714822cab98e90423412fa2b8",
        "balance": 0,
        "futures_session_rpl": 0,
        "additional_reserve": 0,
        "cross_collateral_enabled": false,
        "options_vega": 0,
        "futures_pl": 0,
        "fee_balance": 0,
        "projected_delta_total": 0,
        "options_theta_map": {},
        "session_upl": 0,
        "options_delta": 0,
        "equity": 0,
        "projected_initial_margin": 0,
        "spot_reserve": 0,
        "total_pl": 0,
        "margin_balance": 0,
        "currency": "MATIC",
        "available_funds": 0,
        "options_session_rpl": 0,
        "available_withdrawal_funds": 0,
        "options_gamma_map": {}
      },
      {
        "options_value": 0,
        "locked_balance": 0,
        "total_maintenance_margin_usd": 0.4557215915800001,
        "options_vega_map": {},
        "futures_session_upl": 0,
        "portfolio_margining_enabled": true,
        "total_delta_total_usd": -0.958299526,
        "session_rpl": 0,
        "options_gamma": 0,
        "options_session_upl": 0,
        "options_theta": 0,
        "margin_model": "cross_pm",
        "options_pl": 0,
        "initial_margin": 0.000127,
        "limits": {
          "matching_engine": {
            "block_rfq_maker": {
              "rate": 10,
              "burst": 20
            },
            "cancel_all": {
              "rate": 5,
              "burst": 20
            },
            "guaranteed_mass_quotes": {
              "rate": 2,
              "burst": 2
            },
            "maximum_mass_quotes": {
              "rate": 10,
              "burst": 10
            },
            "maximum_quotes": {
              "rate": 500,
              "burst": 500
            },
            "spot": {
              "rate": 5,
              "burst": 20
            },
            "trading": {
              "total": {
                "rate": 5,
                "burst": 20
              }
            }
          },
          "limits_per_currency": false,
          "non_matching_engine": {
            "rate": 20,
            "burst": 100
          }
        },
        "projected_maintenance_margin": 0.000091,
        "delta_total": 0,
        "maintenance_margin": 0.000091,
        "delta_total_map": {},
        "deposit_address": "0x93527d75ab49d44714822cab98e90423412fa2b8",
        "total_initial_margin_usd": 0.640151869,
        "balance": 0,
        "futures_session_rpl": 0,
        "additional_reserve": 0,
        "cross_collateral_enabled": true,
        "options_vega": 0,
        "futures_pl": 0,
        "fee_balance": 0,
        "projected_delta_total": 0,
        "options_theta_map": {},
        "session_upl": 0,
        "options_delta": 0,
        "equity": 0,
        "projected_initial_margin": 0.000127,
        "spot_reserve": 0,
        "total_equity_usd": 2.531977059,
        "total_pl": 0,
        "margin_balance": 0.000503,
        "currency": "PAXG",
        "available_funds": 0.000376,
        "total_margin_balance_usd": 2.531977059,
        "options_session_rpl": 0,
        "available_withdrawal_funds": 0,
        "options_gamma_map": {}
      },
      {
        "options_value": 0,
        "locked_balance": 0,
        "total_maintenance_margin_usd": 0.4557215915800001,
        "options_vega_map": {},
        "futures_session_upl": 0,
        "portfolio_margining_enabled": true,
        "total_delta_total_usd": -0.958299526,
        "session_rpl": 0,
        "options_gamma": 0,
        "options_session_upl": 0,
        "options_theta": 0,
        "margin_model": "cross_pm",
        "options_pl": 0,
        "initial_margin": 0.00748563,
        "limits": {
          "matching_engine": {
            "block_rfq_maker": {
              "rate": 10,
              "burst": 20
            },
            "cancel_all": {
              "rate": 5,
              "burst": 20
            },
            "guaranteed_mass_quotes": {
              "rate": 2,
              "burst": 2
            },
            "maximum_mass_quotes": {
              "rate": 10,
              "burst": 10
            },
            "maximum_quotes": {
              "rate": 500,
              "burst": 500
            },
            "spot": {
              "rate": 5,
              "burst": 20
            },
            "trading": {
              "total": {
                "rate": 5,
                "burst": 20
              }
            }
          },
          "limits_per_currency": false,
          "non_matching_engine": {
            "rate": 20,
            "burst": 100
          }
        },
        "projected_maintenance_margin": 0.00532899,
        "delta_total": 0,
        "maintenance_margin": 0.00532899,
        "delta_total_map": {},
        "total_initial_margin_usd": 0.640151869,
        "balance": 0,
        "futures_session_rpl": 0,
        "additional_reserve": 0,
        "cross_collateral_enabled": true,
        "options_vega": 0,
        "futures_pl": 0,
        "fee_balance": 0,
        "projected_delta_total": 0,
        "options_theta_map": {},
        "session_upl": 0,
        "options_delta": 0,
        "equity": 0,
        "projected_initial_margin": 0.00748563,
        "spot_reserve": 0,
        "total_equity_usd": 2.531977059,
        "total_pl": 0,
        "margin_balance": 0.02960774,
        "currency": "SOL",
        "available_funds": 0.02212211,
        "total_margin_balance_usd": 2.531977059,
        "options_session_rpl": 0,
        "available_withdrawal_funds": 0,
        "options_gamma_map": {}
      },
      {
        "options_value": 0,
        "locked_balance": 0,
        "total_maintenance_margin_usd": 0.4557215915800001,
        "options_vega_map": {},
        "futures_session_upl": 0,
        "portfolio_margining_enabled": true,
        "total_delta_total_usd": -0.958299526,
        "session_rpl": 0,
        "options_gamma": 0,
        "options_session_upl": 0,
        "options_theta": 0,
        "margin_model": "cross_pm",
        "options_pl": 0,
        "initial_margin": 0.000327,
        "limits": {
          "matching_engine": {
            "block_rfq_maker": {
              "rate": 10,
              "burst": 20
            },
            "cancel_all": {
              "rate": 5,
              "burst": 20
            },
            "guaranteed_mass_quotes": {
              "rate": 2,
              "burst": 2
            },
            "maximum_mass_quotes": {
              "rate": 10,
              "burst": 10
            },
            "maximum_quotes": {
              "rate": 500,
              "burst": 500
            },
            "spot": {
              "rate": 5,
              "burst": 20
            },
            "trading": {
              "total": {
                "rate": 5,
                "burst": 20
              }
            }
          },
          "limits_per_currency": false,
          "non_matching_engine": {
            "rate": 20,
            "burst": 100
          }
        },
        "projected_maintenance_margin": 0.000233,
        "delta_total": 0,
        "maintenance_margin": 0.000233,
        "delta_total_map": {},
        "deposit_address": "0x93527d75ab49d44714822cab98e90423412fa2b8",
        "total_initial_margin_usd": 0.640151869,
        "balance": 0,
        "futures_session_rpl": 0,
        "additional_reserve": 0,
        "cross_collateral_enabled": true,
        "options_vega": 0,
        "futures_pl": 0,
        "fee_balance": 0,
        "projected_delta_total": 0,
        "options_theta_map": {},
        "session_upl": 0,
        "options_delta": 0,
        "equity": 0,
        "projected_initial_margin": 0.000327,
        "spot_reserve": 0,
        "total_equity_usd": 2.531977059,
        "total_pl": 0,
        "margin_balance": 0.001294,
        "currency": "STETH",
        "available_funds": 0.000967,
        "total_margin_balance_usd": 2.531977059,
        "options_session_rpl": 0,
        "available_withdrawal_funds": 0,
        "options_gamma_map": {}
      },
      {
        "options_value": 0,
        "locked_balance": 0,
        "total_maintenance_margin_usd": 0.4557215915800001,
        "options_vega_map": {},
        "futures_session_upl": 0.13336,
        "portfolio_margining_enabled": true,
        "total_delta_total_usd": -0.958299526,
        "session_rpl": 0,
        "options_gamma": 0,
        "options_session_upl": 0,
        "options_theta": 0,
        "margin_model": "cross_pm",
        "options_pl": 0,
        "initial_margin": 0.64015187,
        "limits": {
          "matching_engine": {
            "block_rfq_maker": {
              "rate": 10,
              "burst": 20
            },
            "cancel_all": {
              "rate": 5,
              "burst": 20
            },
            "guaranteed_mass_quotes": {
              "rate": 2,
              "burst": 2
            },
            "maximum_mass_quotes": {
              "rate": 10,
              "burst": 10
            },
            "maximum_quotes": {
              "rate": 500,
              "burst": 500
            },
            "spot": {
              "rate": 5,
              "burst": 20
            },
            "trading": {
              "total": {
                "rate": 5,
                "burst": 20
              }
            }
          },
          "limits_per_currency": false,
          "non_matching_engine": {
            "rate": 20,
            "burst": 100
          }
        },
        "projected_maintenance_margin": 0.45572159,
        "delta_total": -1.95833,
        "maintenance_margin": 0.45572159,
        "delta_total_map": {
          "eth_usdc": -0.001
        },
        "deposit_address": "0x93527d75ab49d44714822cab98e90423412fa2b8",
        "total_initial_margin_usd": 0.640151869,
        "balance": 0.01393577,
        "futures_session_rpl": 0,
        "additional_reserve": 0,
        "cross_collateral_enabled": true,
        "options_vega": 0,
        "futures_pl": 0.14667,
        "fee_balance": 0,
        "projected_delta_total": -1.95833,
        "options_theta_map": {},
        "session_upl": 0.13336,
        "options_delta": 0,
        "equity": 0.14729577,
        "projected_initial_margin": 0.64015187,
        "spot_reserve": 0,
        "total_equity_usd": 2.531977059,
        "total_pl": 0.14667,
        "margin_balance": 2.53197706,
        "currency": "USDC",
        "available_funds": 1.89182519,
        "total_margin_balance_usd": 2.531977059,
        "options_session_rpl": 0,
        "available_withdrawal_funds": 0.00048209,
        "options_gamma_map": {}
      },
      {
        "options_value": 0,
        "locked_balance": 0,
        "total_maintenance_margin_usd": 0.4557215915800001,
        "options_vega_map": {},
        "futures_session_upl": 0,
        "portfolio_margining_enabled": true,
        "total_delta_total_usd": -0.958299526,
        "session_rpl": 0,
        "options_gamma": 0,
        "options_session_upl": 0,
        "options_theta": 0,
        "margin_model": "cross_pm",
        "options_pl": 0,
        "initial_margin": 0.640729,
        "limits": {
          "matching_engine": {
            "block_rfq_maker": {
              "rate": 10,
              "burst": 20
            },
            "cancel_all": {
              "rate": 5,
              "burst": 20
            },
            "guaranteed_mass_quotes": {
              "rate": 2,
              "burst": 2
            },
            "maximum_mass_quotes": {
              "rate": 10,
              "burst": 10
            },
            "maximum_quotes": {
              "rate": 500,
              "burst": 500
            },
            "spot": {
              "rate": 5,
              "burst": 20
            },
            "trading": {
              "total": {
                "rate": 5,
                "burst": 20
              }
            }
          },
          "limits_per_currency": false,
          "non_matching_engine": {
            "rate": 20,
            "burst": 100
          }
        },
        "projected_maintenance_margin": 0.456132,
        "delta_total": 0,
        "maintenance_margin": 0.456132,
        "delta_total_map": {},
        "deposit_address": "0x93527d75ab49d44714822cab98e90423412fa2b8",
        "total_initial_margin_usd": 0.640151869,
        "balance": 0,
        "futures_session_rpl": 0,
        "additional_reserve": 0,
        "cross_collateral_enabled": true,
        "options_vega": 0,
        "futures_pl": 0,
        "fee_balance": 0,
        "projected_delta_total": 0,
        "options_theta_map": {},
        "session_upl": 0,
        "options_delta": 0,
        "equity": 0,
        "projected_initial_margin": 0.640729,
        "spot_reserve": 0,
        "total_equity_usd": 2.531977059,
        "total_pl": 0,
        "margin_balance": 2.534258,
        "currency": "USDE",
        "available_funds": 1.893529,
        "total_margin_balance_usd": 2.531977059,
        "options_session_rpl": 0,
        "available_withdrawal_funds": 0,
        "options_gamma_map": {}
      },
      {
        "options_value": 0,
        "locked_balance": 0,
        "total_maintenance_margin_usd": 0.4557215915800001,
        "options_vega_map": {},
        "futures_session_upl": 0,
        "portfolio_margining_enabled": true,
        "total_delta_total_usd": -0.958299526,
        "session_rpl": 0,
        "options_gamma": 0,
        "options_session_upl": 0,
        "options_theta": 0,
        "margin_model": "cross_pm",
        "options_pl": 0,
        "initial_margin": 0.640408,
        "limits": {
          "matching_engine": {
            "block_rfq_maker": {
              "rate": 10,
              "burst": 20
            },
            "cancel_all": {
              "rate": 5,
              "burst": 20
            },
            "guaranteed_mass_quotes": {
              "rate": 2,
              "burst": 2
            },
            "maximum_mass_quotes": {
              "rate": 10,
              "burst": 10
            },
            "maximum_quotes": {
              "rate": 500,
              "burst": 500
            },
            "spot": {
              "rate": 5,
              "burst": 20
            },
            "trading": {
              "total": {
                "rate": 5,
                "burst": 20
              }
            }
          },
          "limits_per_currency": false,
          "non_matching_engine": {
            "rate": 20,
            "burst": 100
          }
        },
        "projected_maintenance_margin": 0.455904,
        "delta_total": 0,
        "maintenance_margin": 0.455904,
        "delta_total_map": {},
        "deposit_address": "0x93527d75ab49d44714822cab98e90423412fa2b8",
        "total_initial_margin_usd": 0.640151869,
        "balance": 0,
        "futures_session_rpl": 0,
        "additional_reserve": 0,
        "cross_collateral_enabled": true,
        "options_vega": 0,
        "futures_pl": 0,
        "fee_balance": 0,
        "projected_delta_total": 0,
        "options_theta_map": {},
        "session_upl": 0,
        "options_delta": 0,
        "equity": 0,
        "projected_initial_margin": 0.640408,
        "spot_reserve": 0,
        "total_equity_usd": 2.531977059,
        "total_pl": 0,
        "margin_balance": 2.53299,
        "currency": "USDT",
        "available_funds": 1.892582,
        "total_margin_balance_usd": 2.531977059,
        "options_session_rpl": 0,
        "available_withdrawal_funds": 0,
        "options_gamma_map": {}
      },
      {
        "options_value": 0,
        "locked_balance": 0,
        "total_maintenance_margin_usd": 0.4557215915800001,
        "options_vega_map": {},
        "futures_session_upl": 0,
        "portfolio_margining_enabled": true,
        "total_delta_total_usd": -0.958299526,
        "session_rpl": 0,
        "options_gamma": 0,
        "options_session_upl": 0,
        "options_theta": 0,
        "margin_model": "cross_pm",
        "options_pl": 0,
        "initial_margin": 0.57347,
        "limits": {
          "matching_engine": {
            "block_rfq_maker": {
              "rate": 10,
              "burst": 20
            },
            "cancel_all": {
              "rate": 5,
              "burst": 20
            },
            "guaranteed_mass_quotes": {
              "rate": 2,
              "burst": 2
            },
            "maximum_mass_quotes": {
              "rate": 10,
              "burst": 10
            },
            "maximum_quotes": {
              "rate": 500,
              "burst": 500
            },
            "spot": {
              "rate": 5,
              "burst": 20
            },
            "trading": {
              "total": {
                "rate": 5,
                "burst": 20
              }
            }
          },
          "limits_per_currency": false,
          "non_matching_engine": {
            "rate": 20,
            "burst": 100
          }
        },
        "projected_maintenance_margin": 0.408251,
        "delta_total": 0,
        "maintenance_margin": 0.408251,
        "delta_total_map": {},
        "deposit_address": "0x93527d75ab49d44714822cab98e90423412fa2b8",
        "total_initial_margin_usd": 0.640151869,
        "balance": 0,
        "futures_session_rpl": 0,
        "additional_reserve": 0,
        "cross_collateral_enabled": true,
        "options_vega": 0,
        "futures_pl": 0,
        "fee_balance": 0,
        "projected_delta_total": 0,
        "options_theta_map": {},
        "session_upl": 0,
        "options_delta": 0,
        "equity": 0,
        "projected_initial_margin": 0.57347,
        "spot_reserve": 0,
        "total_equity_usd": 2.531977059,
        "total_pl": 0,
        "margin_balance": 2.268232,
        "currency": "USYC",
        "available_funds": 1.694762,
        "total_margin_balance_usd": 2.531977059,
        "options_session_rpl": 0,
        "available_withdrawal_funds": 0,
        "options_gamma_map": {}
      },
      {
        "options_value": 0,
        "locked_balance": 0,
        "options_vega_map": {},
        "futures_session_upl": 0,
        "portfolio_margining_enabled": true,
        "session_rpl": 0,
        "options_gamma": 0,
        "options_session_upl": 0,
        "options_theta": 0,
        "margin_model": "segregated_pm",
        "options_pl": 0,
        "initial_margin": 0,
        "limits": {
          "matching_engine": {
            "block_rfq_maker": {
              "rate": 10,
              "burst": 20
            },
            "cancel_all": {
              "rate": 5,
              "burst": 20
            },
            "guaranteed_mass_quotes": {
              "rate": 2,
              "burst": 2
            },
            "maximum_mass_quotes": {
              "rate": 10,
              "burst": 10
            },
            "maximum_quotes": {
              "rate": 500,
              "burst": 500
            },
            "spot": {
              "rate": 5,
              "burst": 20
            },
            "trading": {
              "total": {
                "rate": 5,
                "burst": 20
              }
            }
          },
          "limits_per_currency": false,
          "non_matching_engine": {
            "rate": 20,
            "burst": 100
          }
        },
        "projected_maintenance_margin": 0,
        "delta_total": 0,
        "maintenance_margin": 0,
        "delta_total_map": {},
        "balance": 0,
        "futures_session_rpl": 0,
        "additional_reserve": 0,
        "cross_collateral_enabled": false,
        "options_vega": 0,
        "futures_pl": 0,
        "fee_balance": 0,
        "projected_delta_total": 0,
        "options_theta_map": {},
        "session_upl": 0,
        "options_delta": 0,
        "equity": 0,
        "projected_initial_margin": 0,
        "spot_reserve": 0,
        "total_pl": 0,
        "margin_balance": 0,
        "currency": "XRP",
        "available_funds": 0,
        "options_session_rpl": 0,
        "available_withdrawal_funds": 0,
        "options_gamma_map": {}
      }
    ],
    "self_trading_reject_mode": "reject_taker",
    "interuser_transfers_enabled": false,
    "referrer_id": null
  },
  "usIn": 1771198046292033,
  "usOut": 1771198046352117,
  "usDiff": 60084,
  "testnet": false
}

{
  "method": "private/get_account_summary",
  "params": {
    "currency": "ETH",
    "extended": true
  },
  "jsonrpc": "2.0",
  "id": 5
}
access-control-allow-headers: Authorization,User-Agent,Range,X-Requested-With,Content-Type,Partner
access-control-allow-methods: GET, POST, OPTIONS
access-control-allow-origin: https://www.deribit.com
cache-control: no-store
cf-cache-status: DYNAMIC
cf-ray: 9ce895d0ec49ec6a-SIN
content-encoding: gzip
content-length: 1045
content-type: application/json
date: Sun, 15 Feb 2026 23:29:04 GMT
server: cloudflare
strict-transport-security: max-age=15768000
vary: Origin,Authorization,Partner, accept-encoding
x-frame-options: SAMEORIGIN
--------------------------------------------------------------------------------
{
  "jsonrpc": "2.0",
  "id": 5,
  "result": {
    "options_value": 0,
    "locked_balance": 0,
    "mmp_enabled": false,
    "total_maintenance_margin_usd": 0.4560793992520001,
    "interuser_transfers_enabled": false,
    "options_vega_map": {},
    "futures_session_upl": -0.000032,
    "portfolio_margining_enabled": true,
    "system_name": "MwaHaHa2020_1",
    "total_delta_total_usd": -0.959942587,
    "session_rpl": 0,
    "options_gamma": 0,
    "creation_timestamp": 1607821349961,
    "id": 148510,
    "username": "MwaHaHa2020_1",
    "options_session_upl": 0,
    "options_theta": 0,
    "margin_model": "cross_pm",
    "options_pl": 0,
    "initial_margin": 0.000327,
    "limits": {
      "matching_engine": {
        "block_rfq_maker": {
          "rate": 10,
          "burst": 20
        },
        "cancel_all": {
          "rate": 5,
          "burst": 20
        },
        "guaranteed_mass_quotes": {
          "rate": 2,
          "burst": 2
        },
        "maximum_mass_quotes": {
          "rate": 10,
          "burst": 10
        },
        "maximum_quotes": {
          "rate": 500,
          "burst": 500
        },
        "spot": {
          "rate": 5,
          "burst": 20
        },
        "trading": {
          "total": {
            "rate": 5,
            "burst": 20
          }
        }
      },
      "limits_per_currency": false,
      "non_matching_engine": {
        "rate": 20,
        "burst": 100
      }
    },
    "type": "subaccount",
    "projected_maintenance_margin": 0.000233,
    "delta_total": 0.000511,
    "block_rfq_self_match_prevention": false,
    "maintenance_margin": 0.000233,
    "change_margin_model_api_limit": {
      "timeframe": 86400000,
      "rate": 5
    },
    "delta_total_map": {
      "eth_usd": 0.000510582
    },
    "email": "ven.ajie@protonmail.com",
    "deposit_address": "0x93527d75ab49d44714822cab98e90423412fa2b8",
    "total_initial_margin_usd": 0.640652049,
    "balance": 0.000031,
    "futures_session_rpl": 0,
    "additional_reserve": 0,
    "cross_collateral_enabled": true,
    "options_vega": 0,
    "futures_pl": -0.000028,
    "receive_notifications": false,
    "fee_balance": 0,
    "projected_delta_total": 0.000511,
    "options_theta_map": {},
    "session_upl": -0.000032,
    "options_delta": 0,
    "equity": -0.000001,
    "referrer_id": null,
    "projected_initial_margin": 0.000327,
    "spot_reserve": 0,
    "total_equity_usd": 2.532674183,
    "security_keys_enabled": true,
    "self_trading_reject_mode": "reject_taker",
    "login_enabled": false,
    "trading_products_details": [
      {
        "enabled": true,
        "product": "perpetual",
        "overwriteable": true,
        "requires_consent": false
      },
      {
        "enabled": true,
        "product": "futures",
        "overwriteable": true,
        "requires_consent": false
      },
      {
        "enabled": true,
        "product": "options",
        "overwriteable": true,
        "requires_consent": false
      },
      {
        "enabled": true,
        "product": "future_combos",
        "overwriteable": true,
        "requires_consent": false
      },
      {
        "enabled": true,
        "product": "option_combos",
        "overwriteable": true,
        "requires_consent": false
      },
      {
        "enabled": true,
        "product": "spots",
        "overwriteable": true,
        "requires_consent": false
      }
    ],
    "total_pl": -0.000028,
    "mandatory_tfa": false,
    "self_trading_extended_to_subaccounts": false,
    "margin_balance": 0.001293,
    "currency": "ETH",
    "available_funds": 0.000966,
    "total_margin_balance_usd": 2.532674183,
    "options_session_rpl": 0,
    "available_withdrawal_funds": 0,
    "options_gamma_map": {}
  },
  "usIn": 1771198144240414,
  "usOut": 1771198144243271,
  "usDiff": 2857,
  "testnet": false
}

{
  "method": "private/buy",
  "params": {
    "instrument_name": "ETH-PERPETUAL",
    "amount": 1,
    "type": "limit",
    "label": "test-123",
    "price": 1000,
    "time_in_force": "good_til_day",
    "post_only": true,
    "linked_order_type": "one_triggers_other",
    "trigger_fill_condition": "incremental",
    "otoco_config": [
      {
        "amount": 1,
        "direction": "sell",
        "type": "take_limit",
        "label": "test-123",
        "price": 2000,
        "reduce_only": true,
        "time_in_force": "good_til_cancelled",
        "post_only": true,
        "trigger_price": 999,
        "trigger": "last_price"
      }
    ]
  },
  "jsonrpc": "2.0",
  "id": 9
}
access-control-allow-headers: Authorization,User-Agent,Range,X-Requested-With,Content-Type,Partner
access-control-allow-methods: GET, POST, OPTIONS
access-control-allow-origin: https://www.deribit.com
cache-control: no-store
cf-cache-status: DYNAMIC
cf-ray: 9ce8a1659cec9c6b-SIN
content-encoding: gzip
content-length: 426
content-type: application/json
date: Sun, 15 Feb 2026 23:36:58 GMT
server: cloudflare
strict-transport-security: max-age=15768000
vary: Origin,Authorization,Partner, accept-encoding
x-frame-options: SAMEORIGIN
--------------------------------------------------------------------------------
{
  "jsonrpc": "2.0",
  "id": 9,
  "result": {
    "order": {
      "label": "test-123",
      "price": 1000,
      "user_id": 148510,
      "amount": 1,
      "direction": "buy",
      "time_in_force": "good_til_day",
      "instrument_name": "ETH-PERPETUAL",
      "web": false,
      "api": true,
      "order_id": "ETH-109559973994",
      "creation_timestamp": 1771198618609,
      "replaced": false,
      "filled_amount": 0,
      "last_update_timestamp": 1771198618609,
      "trigger_fill_condition": "incremental",
      "post_only": true,
      "reduce_only": false,
      "average_price": 0,
      "mmp": false,
      "contracts": 1,
      "reject_post_only": false,
      "order_state": "open",
      "order_type": "limit",
      "is_liquidation": false,
      "risk_reducing": false,
      "oto_order_ids": [
        "ETH-OTO-6910166"
      ]
    },
    "trades": []
  },
  "usIn": 1771198618603260,
  "usOut": 1771198618613310,
  "usDiff": 10050,
  "testnet": false
}