-- Amend doi_register table by adding columns
-- DO NOT RUN - this DDL is now executed by script `update_modified_doi_register.py`


--ALTER TABLE `jper`.`doi_register`
--ADD COLUMN `category` CHAR(3) NULL DEFAULT NULL COMMENT 'Type of resource.  Value is between 1 and 3 characters. First character one of: J-journal, B-book, C-conference, R-report, P-pre-print, V-review, O-other. Second & third characters, if present, further refine the categorisation.' AFTER `updated`,
--ADD COLUMN `has_pdf` TINYINT NULL DEFAULT NULL COMMENT 'Indicates if text (e.g. PDF) supplied or not.  Value 1 = Full-text, NULL = Metadata only (no full text).' AFTER `category`,
--ADD INDEX `created_updated` (`created` ASC, `updated` ASC) VISIBLE;
--
--ALTER TABLE `jper`.`doi_register`
--CHANGE COLUMN `updated` `updated` DATETIME NOT NULL COMMENT 'Value is always set deliberately, not automatically by MySQL.';
--
