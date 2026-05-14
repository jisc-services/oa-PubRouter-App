ALTER TABLE `jper`.`content_log` 
CHANGE COLUMN `user_id` `acc_id` INT UNSIGNED NOT NULL COMMENT 'Organisation account ID - foreign key to an Account record (most likely a Repository account, but could be Publisher account).' ;
