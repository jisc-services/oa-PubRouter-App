-- Create `job` table used by `schedule.py`
--

CREATE TABLE IF NOT EXISTS `job` (
      `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
      `created` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      `server_prog` VARCHAR(25) NOT NULL COMMENT 'Dot separated string: \"Server\".\"Program-name\"',
      `status` TINYINT NULL COMMENT 'Job status.' ,
      `priority` TINYINT NULL DEFAULT NULL COMMENT 'Job priority.' ,
      `end_time` DATETIME NULL DEFAULT NULL,
      `next_start` DATETIME NULL DEFAULT NULL,
      `last_run` DATETIME NULL DEFAULT NULL,
      `periodicity` VARCHAR(20) NULL DEFAULT NULL COMMENT 'Frequency with which job repeats.',
      `json` VARCHAR(5000) NULL COMMENT 'Relatively large size in case the JSON contains a large Job Result exception.',
  PRIMARY KEY (`id`),
  INDEX `server_prog` (`server_prog` ASC) VISIBLE,
  INDEX `priority_nextstart` (`priority` ASC, `next_start` ASC) VISIBLE)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8mb4
COMMENT = 'Stores job information for schedule';
