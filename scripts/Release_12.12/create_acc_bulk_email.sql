-- Create acc_bulk_email table
--
CREATE TABLE `acc_bulk_email` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `created` datetime NOT NULL,
  `status` char(1) DEFAULT NULL COMMENT 'Indicator: "H": Highlight; "D": Deleted; "R": Resolved/done',
  `ac_type` char(1) NOT NULL COMMENT 'Type of bulk email: ''A'' - all accounts; ''R'' - repository accounts; ''P'' - publisher accounts',
  `subject` varchar(200) NOT NULL,
  `body` varchar(7000) NOT NULL COMMENT 'Subject & Body of email.',
  `json` varchar(3000) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `actype_status` (`ac_type` ASC,`status` ASC) VISIBLE,
  KEY `created_status` (`created` ASC,`status` ASC) VISIBLE
) ENGINE=InnoDB AUTO_INCREMENT=10 DEFAULT CHARSET=utf8mb4;
