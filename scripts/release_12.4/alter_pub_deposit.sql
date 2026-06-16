-- NOT implementing this, using raw notifications as source of data for pub-doi-report

-- Alter pub_deposit table to support new publisher report

--ALTER TABLE `jper`.`pub_deposit`
--ADD COLUMN `doi` VARCHAR(255) NULL DEFAULT NULL COMMENT 'Article DOI (only present where matched is 1).' AFTER `err_emailed`,
--ADD COLUMN `repo_ids` VARCHAR(1000) NULL DEFAULT NULL COMMENT 'String of \"|\" separated Repo-account IDs to which notification was matched.' AFTER `doi`,
--DROP INDEX `pubid_created` ,
--ADD INDEX `pubid_created_matched` (`pub_id` ASC, `created` ASC, `matched` ASC) VISIBLE;
--;
