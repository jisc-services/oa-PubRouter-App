-- Changes to tables & their indexes (except for 'account' table)
-- *NOTE*: THESE HAVE BEEN APPLIED TO *ALL* ENVIRONMENTS DURING DEVELOPMENT

-- acc_notes_emails
ALTER TABLE `jper`.`acc_notes_emails`
DROP INDEX `type` ,
ADD INDEX `created` (`created` ASC) VISIBLE;


-- notification
ALTER TABLE `jper`.`notification`
DROP INDEX `prov_route` ;
-- TODO Sept 2022
ALTER TABLE `jper`.`notification`
ADD INDEX `analysis_date_prov_id` (`analysis_date` ASC, `prov_id` ASC) VISIBLE,
DROP INDEX `analysis_date` ;
;


-- org_identifiers
ALTER TABLE `jper`.`org_identifiers`
DROP INDEX `name` ;


-- sword_deposit
ALTER TABLE `jper`.`sword_deposit`
ADD INDEX `repoid_depositdate` (`repo_id` ASC, `deposit_date` ASC) VISIBLE,
ADD INDEX `noteid_repoid_metastatus` (`note_id` ASC, `repo_id` ASC, `metadata_status` ASC) VISIBLE,
ADD INDEX `repoid_doi_metastatus` (`note_id` ASC, `repo_id` ASC, `metadata_status` ASC) VISIBLE;

ALTER TABLE `jper`.`sword_deposit`
DROP INDEX `doi` ,
DROP INDEX `note_id` ,
DROP INDEX `metadata_status` ,
DROP INDEX `repo_id` ;

