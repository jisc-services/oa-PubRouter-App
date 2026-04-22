CREATE TABLE `acc_notes_emails` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `created` datetime NOT NULL,
  `acc_id` int unsigned NOT NULL COMMENT 'Foreign key to corresponding Account Id.',
  `type` char(1) NOT NULL COMMENT 'Type of entry:  "E": Email; "N": Note',
  `status` char(1) DEFAULT NULL COMMENT 'Indicator: "D" - Deleted record; "H"-Highlighted.',
  `json` varchar(7000) DEFAULT NULL COMMENT 'Holds record structure.',
  PRIMARY KEY (`id`),
  KEY `ac_id` (`acc_id`),
  KEY `type` (`type`)
)
ENGINE=InnoDB
DEFAULT CHARSET=UTF8MB4
COMMENT='Table holds Notes & Emails associated with particular accounts';
