-- In Account table, change role value from string to single char
--   "admin" --> "A"
--   "repository" --> "R"
--   "publisher" --> "P"
-- AND change indexes

-- Change 'role' values to single upper case character
UPDATE account set role = UPPER(LEFT(role, 1));

-- Amend 'role' column to store a single character
-- Amend other columns to have ascci character sets
ALTER TABLE `jper`.`account`
CHANGE COLUMN `uuid` `uuid` CHAR(32) CHARACTER SET 'ascii' COLLATE 'ascii_general_ci' NOT NULL COMMENT '32 character UUID - \"public\" accound ID.' ,
CHANGE COLUMN `deleted_date` `deleted_date` CHAR(20) CHARACTER SET 'ascii' COLLATE 'ascii_bin' NULL DEFAULT NULL COMMENT 'Saved as String as does not need processing as a date. Also allows it to be indexed efficiently, since we are  really only interested in whether it is NULL or not.' ,
CHANGE COLUMN `api_key` `api_key` VARCHAR(45) CHARACTER SET 'ascii' COLLATE 'ascii_general_ci' NOT NULL ,
CHANGE COLUMN `role` `role` CHAR(1) CHARACTER SET 'ascii' COLLATE 'ascii_bin' NOT NULL ,
CHANGE COLUMN `r_excluded_providers` `r_excluded_providers` VARCHAR(1000) CHARACTER SET 'ascii' COLLATE 'ascii_general_ci' NULL DEFAULT NULL COMMENT 'JSON field: repository_data.matching_config.exluded_provider_ids' ,
CHANGE COLUMN `p_test_start` `p_test_start` VARCHAR(10) CHARACTER SET 'ascii' COLLATE 'ascii_bin' NULL DEFAULT NULL COMMENT 'JSON: publisher_data.testing.start' ,
ADD INDEX `deldate_role_live_status` (`deleted_date`(7), `role`, `live_date`, `status`) VISIBLE,
ADD INDEX `role_status` (`role` ASC, `status` ASC) VISIBLE;

ALTER TABLE `jper`.`account`
DROP INDEX `role` ,
DROP INDEX `deleted` ,
DROP INDEX `status` ,
DROP INDEX `live` ;
;
