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
        'config_key': 'api.ebay_commerce_daily_limit',
        'label': 'eBay Commerce API daily limit',
        'value': '100',
        'value_type': 'integer',
        'description': 'Maximum eBay Commerce API calls allowed per day.',
    },
    {
        'section': 'api',
        'config_key': 'api.ebay_fulfillment_daily_limit',
        'label': 'eBay Fulfillment API daily limit',
        'value': '100',
        'value_type': 'integer',
        'description': 'Maximum eBay Fulfillment API calls allowed per day.',
    },
    {
        'section': 'api',
        'config_key': 'api.ebay_bestseller_daily_limit',
        'label': 'eBay Bestseller API daily limit',
        'value': '100',
        'value_type': 'integer',
        'description': 'Maximum eBay Bestseller API calls allowed per day.',
    },
]

