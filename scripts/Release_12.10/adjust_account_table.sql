-- Add 'tech_contacts' column to account table.
ALTER TABLE `jper`.`account` 
ADD COLUMN `tech_contact_emails` VARCHAR(400) NULL DEFAULT NULL COMMENT 'Technical contact emails' AFTER `contact_email`;
