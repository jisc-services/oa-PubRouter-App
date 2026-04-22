-- Remove column & index for transitional code related to UUID (hangover from Elasticsearch era)

ALTER TABLE `jper`.`notification`
DROP COLUMN `trans_uuid`,
DROP INDEX `orig_uuid` ;
;