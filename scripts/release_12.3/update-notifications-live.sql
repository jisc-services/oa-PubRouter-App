-- Live: Update notification records `links_json` column to replace "url" values by "cloc" values for Router links
USE jper;

-- Create temporary table
CREATE TABLE notification_cpy LIKE notification;
INSERT INTO notification_cpy SELECT * FROM notification;

-- Check number of rows expecting to update
SELECT count(*) FROM notification_cpy WHERE links_json LIKE "%/content%";
SELECT id, links_json FROM notification_cpy WHERE links_json LIKE "%/content%" LIMIT 10;

-- Perform the update (NB. this version allows for v3 ONLY)
-- https://XXXX.jisc.ac.uk
UPDATE notification_cpy
SET links_json = REGEXP_REPLACE(links_json, '"url":"https://XXXX.jisc.ac.uk/api/v3/notification/[0-9]+/content/?','"cloc":"')
WHERE links_json LIKE "%/content%";

-- Check number of records that still have '/content' in them - SHOULD be 0
SELECT count(*) FROM notification_cpy WHERE links_json LIKE '%/content%';
-- SELECT * FROM notification_cpy WHERE links_json LIKE '%/content%';

-- Check number of records with "cloc" in them - should equal initial number with '/content' in them
SELECT count(*) FROM notification_cpy WHERE links_json LIKE '%"cloc"%';
SELECT * FROM notification_cpy WHERE links_json LIKE '%"cloc"%' LIMIT 10;

-- Rename original table & replace by modified table
RENAME TABLE notification TO notification_original;
RENAME TABLE notification_cpy TO notification;
