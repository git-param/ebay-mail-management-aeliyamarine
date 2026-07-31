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
    {'section': 'pms', 'config_key': 'pms.limit.sold_posting', 'label': 'PMS sold posting score limit', 'value': '20', 'value_type': 'integer', 'description': 'Maximum daily PMS score for Sold Posting.'},
    {'section': 'pms', 'config_key': 'pms.limit.m2m_vip_followups', 'label': 'PMS M2M/VIP follow-ups score limit', 'value': '25', 'value_type': 'integer', 'description': 'Maximum daily PMS score for M2M queries and VIP follow-ups.'},
    {'section': 'pms', 'config_key': 'pms.limit.tracking_sheet', 'label': 'PMS tracking sheet score limit', 'value': '25', 'value_type': 'integer', 'description': 'Maximum daily PMS score for tracking sheet work.'},
    {'section': 'pms', 'config_key': 'pms.limit.purchase_sheet', 'label': 'PMS purchase sheet score limit', 'value': '10', 'value_type': 'integer', 'description': 'Maximum daily PMS score for purchase sheet work.'},
    {'section': 'pms', 'config_key': 'pms.limit.booking', 'label': 'PMS booking score limit', 'value': '10', 'value_type': 'integer', 'description': 'Maximum daily PMS score for booking work.'},
    {'section': 'pms', 'config_key': 'pms.limit.other_general_work', 'label': 'PMS other general work score limit', 'value': '10', 'value_type': 'integer', 'description': 'Maximum daily PMS score for other general work.'},
    {'section': 'pms', 'config_key': 'pms.limit.message_type_default', 'label': 'PMS message type score limit', 'value': '10', 'value_type': 'integer', 'description': 'Default maximum score for each dynamic message type field.'},
]

