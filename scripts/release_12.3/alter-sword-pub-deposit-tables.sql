-- Updates to table structure to support new emailing of recent errors func

ALTER TABLE `jper`.`pub_deposit`
ADD COLUMN `err_emailed` TINYINT NULL DEFAULT NULL COMMENT 'Indicates if error included in an email.' AFTER `sword_in_progress`;

ALTER TABLE `jper`.`sword_deposit`
ADD COLUMN `err_emailed` TINYINT NULL DEFAULT NULL COMMENT 'Indicates if error included in an email.' AFTER `edit_iri`;
