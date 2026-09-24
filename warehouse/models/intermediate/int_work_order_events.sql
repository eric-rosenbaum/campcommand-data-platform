select *
from {{ ref('int_app_events_deduplicated') }}
where event_entity = 'work_order'
