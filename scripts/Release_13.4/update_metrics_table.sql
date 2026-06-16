--
--	Change JSON dict contents: remove the {"extra": ..... } field, leaving the dict that was the value of "extra".
--
use jper;

-- Remove the text `{"extra":` from start of JSON string
update metrics set json = REGEXP_REPLACE(json, '^\\{"extra":', '')
where json is not null
;

-- Remove the last `}` from end of JSON string
update metrics set json = REGEXP_REPLACE(json, '\\}\\}$', '}')
where json is not null
;

-- Check first 100 recs with JSON values
select * from metrics
where json is not null
limit 100
;