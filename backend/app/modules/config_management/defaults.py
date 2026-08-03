DEFAULT_CONFIGS = [
    {
        'section': 'offer',
        'config_key': 'offer.high_value_amount',
        'label': 'High value amount',
        'value': '500',
        'value_type': 'decimal',
        'description': 'Offer entries are high value when unit offer or quantity multiplied by offer amount reaches this value.',
    },
    {
        'section': 'api',
        'config_key': 'api.ebay_daily_api_limit',
        'label': 'eBay daily API limit',
        'value': '100',
        'value_type': 'integer',
        'description': 'Maximum eBay API calls allowed per day.',
    },
]

