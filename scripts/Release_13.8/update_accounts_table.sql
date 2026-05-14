--
--	In `accounts` table, Change JSON dict contents:
--          {"level"  -->  {"level_p: 5, "level_h"
--
use jper;

-- {"level"  -->  {"level_p: 5, "level_h" within JSON string
update account set json = REGEXP_REPLACE(json, '"level"', '"level_p": 5, "level_h"', 1, 1)
where json is not null
and role = 'R'
;
