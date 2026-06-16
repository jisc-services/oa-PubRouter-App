-- Add column for storing metrics_json which we may want to retrieve separate from whole notification

ALTER TABLE `jper`.`notification`
ADD COLUMN `metrics_json` VARCHAR(500) NULL DEFAULT NULL COMMENT 'Dictionary of notification metrics. Will be NULL for UnroutedNotification.' AFTER `links_json`
;