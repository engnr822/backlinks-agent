"""Deterministic citation copy using canonical registry facts, without API calls."""


def registry_descriptions(business):
    nap = business['nap']
    name = nap['listing_name'].strip()
    category = business.get('primary_category', '').strip()
    location = ', '.join(str(nap.get(k, '')).strip() for k in ('city', 'state') if nap.get(k))
    if not name or not category or not location:
        raise ValueError('Registry descriptions require listing name, category and city')
    referral = business.get('location_type') == 'service_area'
    if referral:
        short = f'{name}: {category} referrals in {location}.'
        medium = (f'{name} connects customers in {location} with independent providers for '
                  f'{category.lower()} services. This is a referral website and does not perform contracting work.')
    else:
        short = f'{name}: {category} in {location}.'
        medium = short
    if len(short) > 150:
        # Preserve the whole canonical name and referral role, never clip words.
        short = f'{name}: ' + ('referral service' if referral else category) + '.'
    area = nap.get('service_area') or []
    area_text = ', '.join(str(value) for value in area)
    long = medium + (f' Service area: {area_text}.' if area_text else '')
    result = {'short': short, 'medium': medium, 'long': long}
    for key, limit in [('short', 150), ('medium', 300), ('long', 750)]:
        if len(result[key]) > limit:
            raise ValueError(f'Registry {key} description exceeds {limit} characters; review business data')
    return result
