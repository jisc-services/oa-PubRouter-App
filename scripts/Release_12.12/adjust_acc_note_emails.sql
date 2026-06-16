-- Script to alter table in order to support Bulk Email functionality
--
ALTER TABLE `jper`.`acc_notes_emails` 
ADD COLUMN `bulk_email_id` INT UNSIGNED NULL DEFAULT NULL COMMENT 'Foreign key to `acc_bulk_email` record. Will only be populated for Bulk emails (in which case json will be empty as the email text etc. will be found in that record).' AFTER `json`,
CHANGE COLUMN `type` `type` CHAR(1) NOT NULL COMMENT 'Type of entry:  \"E\": Email; \"N\": Note; \"T\": To-do; \"B\": Bulk email.  (If Bulk email, then bulk_email_id will reference the `acc_bulk_email` record that contains the email data).' ,
CHANGE COLUMN `status` `status` CHAR(1) NULL DEFAULT NULL COMMENT 'Indicator: \"H\": Highlight; \"D\": Deleted; \"R\": Resolved/done' ;

-- Adjust index
ALTER TABLE `jper`.`acc_notes_emails` 
DROP INDEX `ac_id` ,
DROP INDEX `created`,
ADD INDEX `acid_type_status` (`acc_id` ASC, `type` ASC,`status` ASC) VISIBLE,
ADD INDEX `created_status` (`created` ASC, `status` ASC) VISIBLE,
ADD INDEX `bulk_email_id` (`bulk_email_id` ASC) VISIBLE
;


