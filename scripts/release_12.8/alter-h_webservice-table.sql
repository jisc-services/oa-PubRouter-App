-- Add 2 columns for storing Notes & an Indicator boolean to h_webservice table

ALTER TABLE `jper`.`h_webservice`
ADD COLUMN `notes` VARCHAR(3000) NULL DEFAULT NULL COMMENT 'Notes to display on webservice screen.',
ADD COLUMN `auto_enable` SMALLINT NULL DEFAULT NULL COMMENT 'Whether web service should be automatically enabled for new Repo accounts or not.'
;