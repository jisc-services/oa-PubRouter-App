--
-- Create `metrics` table
--

CREATE TABLE `metrics` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `start` datetime NOT NULL COMMENT 'Time process started.',
  `duration` decimal(8,3) NOT NULL COMMENT 'Duration in Seconds to 3 decimal places (nnnnn.nnn) for process to complete.',
  `server` varchar(45) DEFAULT NULL COMMENT 'Server on which process runs.',
  `proc_name` varchar(80) NOT NULL COMMENT 'Process name.',
  `measure` varchar(80) DEFAULT NULL COMMENT 'What is being measured (counted).',
  `count` mediumint unsigned DEFAULT NULL COMMENT 'Count.',
  `json` varchar(2000) DEFAULT NULL COMMENT 'Other data',
  PRIMARY KEY (`id`),
  KEY `proc_name` (`proc_name`),
  KEY `start_procname` (`start`,`proc_name`)
)
ENGINE=InnoDB
AUTO_INCREMENT=1
DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
COMMENT='Table stores processing metrics'
;