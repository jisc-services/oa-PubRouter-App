"""
DDL for creating JPER database TABLES

Author: Jisc
"""

JPER_TABLES = {
    "account":
        """
        CREATE TABLE IF NOT EXISTS `account` (     
          `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
          `uuid` CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '32 character UUID - "public" accound ID.',
          `created` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          `updated` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          `deleted_date` char(20) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL COMMENT 'Saved as String as does not need processing as a date. Also allows it to be indexed efficiently, since we are  really only interested in whether it is NULL or not.',
          `api_key` VARCHAR(45) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
          `live_date` DATETIME DEFAULT NULL,
          `contact_email` VARCHAR(100) DEFAULT NULL,
          `tech_contact_emails` VARCHAR(400) DEFAULT NULL COMMENT 'Technical contact emails',
          `role` CHAR(1) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT 'Account type: One of \"A\" - Admin, \"R\" - Repo, \"P\" - Publisher.',
          `org_name` VARCHAR(100) NOT NULL,
          `status` TINYINT DEFAULT NULL COMMENT 'Status, if set has one of these values:\n0 -> Off\n1 -> Okay (On OK)\n2 -> Failing  (Repositories only)\n3 -> Problem (Repositories only)',
          `r_sword_collection` VARCHAR(100) DEFAULT NULL COMMENT 'JSON field: repoository_data.sword.collection',
          `r_repo_name` VARCHAR(100) DEFAULT NULL COMMENT 'JSON field: repoository_data.repository_info.name',
          `r_excluded_providers` VARCHAR(1000) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL COMMENT 'JSON field: repository_data.matching_config.exluded_provider_ids',
          `r_identifiers` VARCHAR(200) CHARACTER SET 'ascii' COLLATE 'ascii_bin' DEFAULT NULL COMMENT 'Stores identifiers JSON list structure.',
          `p_in_test` TINYINT DEFAULT NULL COMMENT 'JSON: publisher_data.in_test',
          `p_test_start` VARCHAR(10) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL COMMENT 'JSON: publisher_data.testing.start',
          `json` VARCHAR(10000) DEFAULT NULL,
          PRIMARY KEY (`id`),
          UNIQUE KEY `uuid_UNIQUE` (`uuid`),
          INDEX `contact` (`contact_email`),
          INDEX `apikey` (`api_key`),
          INDEX `deldate_role_live_status` (`deleted_date`(7),`role`,`live_date`,`status`),
          INDEX `role_status` (`role`,`status`)
        )
        ENGINE = InnoDB
        DEFAULT CHARACTER SET = utf8mb3
        COMMENT = 'Stores account information for Admin, Repository & Publisher organisation accounts.\\nColumns prefixed \"r_\" apply only to Repository accounts.\\nColumns prefixed \"p_\" apply only to Publisher accounts.';
        """,

    "acc_bulk_email":
        """
        CREATE TABLE IF NOT EXISTS `acc_bulk_email` (
          `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
          `created` DATETIME NOT NULL COMMENT 'Created date in this table is NOT set using default CURRENT_TIMESTAMP. but is set (automatically) within Python mysql/dao.py code because for newly inserted records it is then immediately available without re-reading the new record.',
          `status` CHAR(1) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL COMMENT 'Indicator: "H": Highlight; "D": Deleted; "R": Resolved/done',
          `ac_type` CHAR(1) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT 'Type of bulk email: "A" - all accounts; "R" - repository accounts; "P" - publisher accounts',
          `subject` VARCHAR(200) NOT NULL,
          `body` VARCHAR(9000) NOT NULL,
          `json` VARCHAR(15000) CHARACTER SET ascii COLLATE ascii_general_ci DEFAULT NULL COMMENT 'IMPORTANT: ASCII character set as only stores email addresses & numbers. Necessary because use of  UTF8 (which can use upto 4 bytes) reduces size of VARCHAR that can be specified.',
          PRIMARY KEY (`id`),
          INDEX `actype_status` (`ac_type`,`status`) VISIBLE,
          INDEX `created_status` (`created`,`status`) VISIBLE)
        ENGINE = InnoDB
        DEFAULT CHARACTER SET = utf8mb4
        COMMENT = 'Table holds Bulk Emails associated with particular accounts';
        """,

    "acc_notes_emails":
        """
        CREATE TABLE IF NOT EXISTS `acc_notes_emails` (
          `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
          `created` DATETIME NOT NULL COMMENT 'Created date in this table is NOT set using default CURRENT_TIMESTAMP. but is set (automatically) within Python mysql/dao.py code because for newly inserted records it is then immediately available without re-reading the new record.',
          `acc_id` INT UNSIGNED NOT NULL COMMENT 'Foreign key to corresponding Account Id.',
          `type` CHAR(1) CHARACTER SET 'ascii' COLLATE 'ascii_bin' NOT NULL COMMENT 'Type of entry:  "E": Email; "N": Note; "T": To-do; "B": Bulk email.  (If Bulk email, then bulk_email_id will reference the `acc_bulk_email` record that contains the email data).',
          `status` CHAR(1) CHARACTER SET 'ascii' COLLATE 'ascii_bin' DEFAULT NULL COMMENT 'Indicator: "H": Highlight; "D": Deleted; "R": Resolved/done',
          `json` VARCHAR(9000) CHARACTER SET 'utf8mb4' COLLATE 'utf8mb4_0900_ai_ci' NULL DEFAULT NULL COMMENT 'Holds record structure.',
          `bulk_email_id` INT unsigned DEFAULT NULL COMMENT 'Foreign key to `acc_bulk_email` record. Will only be populated for Bulk emails (in which case json will be empty as the email text etc. will be found in that record).',
          PRIMARY KEY (`id`),
          INDEX `bulk_email_id` (`bulk_email_id`) VISIBLE,
          INDEX `acid_type_status` (`acc_id`,`type`,`status`) VISIBLE,
          INDEX `created_status` (`created`,`status`) VISIBLE)
        ENGINE = InnoDB
        DEFAULT CHARACTER SET = utf8mb3
        COMMENT = 'Table holds Notes & Emails associated with particular accounts';
        """,

    "acc_repo_match_params":
        """
        CREATE TABLE IF NOT EXISTS `acc_repo_match_params` (
          `id` INT UNSIGNED NOT NULL COMMENT 'Repository Account ID (in account table)' ,
          `created` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          `updated` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          `has_regex` TINYINT NULL DEFAULT NULL COMMENT 'Indicates whether Name Variants use REGEX.',
          `had_regex` TINYINT NULL DEFAULT NULL COMMENT 'Parameters have included RegEx in the past, (even if they dont currently)',
          `json` VARCHAR(60000) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL COMMENT 'Need to allow for large sets of matching parameters- e.g. large numbers of ORCIDS and grants.   \\n** Hence base64 compressed JSON is stored as ASCII characters (column has ASCII character set) **',
          PRIMARY KEY (`id`)
        ) 
        ENGINE=InnoDB 
        DEFAULT CHARACTER SET = utf8mb3
        COMMENT = 'Table holds Matching Parameters for Repository account with same ID value';
        """,

    "acc_repo_match_params_archived":
        """
        CREATE TABLE IF NOT EXISTS `acc_repo_match_params_archived` (
          `pkid` INT UNSIGNED NOT NULL AUTO_INCREMENT,
          `archived` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Date that the matching params were archived (i.e. replaced by a new set of "active" matching params)',
          `id` INT UNSIGNED NOT NULL COMMENT 'Repository Account ID (in account table)',
          `updated` DATETIME NOT NULL COMMENT 'Original matching params record last updated date.',
          `has_regex` TINYINT NULL DEFAULT NULL COMMENT 'Indicates whether Name Variants use REGEX.',
          `json` VARCHAR(60000) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL COMMENT 'Need to allow for large sets of  matching parameters- e.g. large numbers of ORCIDS and grants.   \\n** Hence base64 compressed JSON is stored as ASCII characters (column has ASCII character set) **',
          PRIMARY KEY (`pkid`),
          INDEX `accid_archived` (`id`,`archived` DESC)
        ) 
        ENGINE=InnoDB 
        DEFAULT CHARACTER SET = utf8mb3
        COMMENT = 'Table holds OLD (archived) Matching Parameters for Repository account with same ID value';
        """,

    "acc_user":
        """
        CREATE TABLE IF NOT EXISTS `acc_user` (
          `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
          `uuid` CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL COMMENT '32 character UUID - \"public\" accound ID.',
          `created` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          `updated` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          `last_success` CHAR(20) CHARACTER SET ascii COLLATE ascii_bin NULL DEFAULT NULL COMMENT 'Date of last successful login.',
          `last_failed` CHAR(20) CHARACTER SET ascii COLLATE ascii_bin NULL DEFAULT NULL COMMENT 'Date of last failed login attempt.',
          `deleted` CHAR(20) CHARACTER SET ascii COLLATE ascii_bin NULL DEFAULT NULL COMMENT 'User deletion date.',
          `acc_id` INT UNSIGNED NOT NULL COMMENT 'Foreign key to (Organisation) Account record with which this user is associated.',
          `username` VARCHAR(110) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
          `role_code` CHAR(1) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'U' COMMENT 'Router role code - One of: "R"-Read-only user, "S"-Standard user, "A"-Org Account Admin, possibly "J"-Jisc Admin, "D"-Developer Admin.',
          `failed_login_count` SMALLINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Number of failed login attempts (reset to 0 on successful login)',
          `json` VARCHAR(8000) NULL DEFAULT NULL,
          PRIMARY KEY (`id`),
          UNIQUE INDEX `username_UNIQUE` (`username` ASC) VISIBLE,
          UNIQUE INDEX `uuid_UNIQUE` (`uuid` ASC) VISIBLE,
          INDEX `accid_role` (`acc_id` ASC, `role_code` ASC, `deleted` ASC) VISIBLE,
          INDEX `deleted` (`deleted` ASC) VISIBLE
          ) ENGINE=InnoDB
        DEFAULT CHARACTER SET = utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        COMMENT = 'Individual user account, associated with an Account record';
        """,

    "cms_ctl":
        """
        CREATE TABLE IF NOT EXISTS `cms_ctl` (
          `cms_type` VARCHAR(15) CHARACTER SET 'ascii' COLLATE 'ascii_bin' NOT NULL COMMENT 'Keyword name by which type of content is known - should NOT contain spaces.',
          `sort_by` CHAR(1) CHARACTER SET ascii COLLATE ascii_bin DEFAULT NULL COMMENT 'Determines sort-order when records are retrieved (& brief-desc displayed on GUI).  NOTE that value must be Non-NULL for records to be retrieved.',
          `updated` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          `brief_desc` VARCHAR(80) NOT NULL COMMENT 'Brief description of content type, e.g. for drop-down list.',
          `json` VARCHAR(10000) DEFAULT NULL COMMENT 'Not sure if this will be needed.',
          PRIMARY KEY (`cms_type`)
        ) ENGINE=InnoDB
        DEFAULT CHARACTER SET = utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        COMMENT='Control table managed content - contains details of each type of managed content.'
        """,

    "cms_html":
        """
        CREATE TABLE IF NOT EXISTS `cms_html` (
          `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
          `created` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          `updated` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          `cms_type` VARCHAR(15) CHARACTER SET 'ascii' COLLATE 'ascii_bin' NOT NULL COMMENT 'Type of content - Foreign Key to entry in content_mgt_ctl table',
          `status` CHAR(1) CHARACTER SET 'ascii' COLLATE 'ascii_bin' DEFAULT NULL COMMENT 'Status, possible values:\\nN - New (not Live)\\nL - Live\\nD - Deleted\\nS - Superseded',
          `sort_value` VARCHAR(40) DEFAULT '' COMMENT 'Value on which to sort records of same content)type to ensure they appear in required order.',
          `json` VARCHAR(10000) DEFAULT NULL COMMENT 'JSON structure will contain the actual content for each of the fields specified in content_mgt_ctl table for this particular cms_type.',
          PRIMARY KEY (`id`),
          INDEX `ctype_status` (`cms_type`,`status`) VISIBLE
        ) ENGINE=InnoDB
        DEFAULT CHARACTER SET = utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        COMMENT='Contains managed content (user editable) for display on HTML pages.';
        """,

    "content_log":
        """
        CREATE TABLE IF NOT EXISTS `content_log` (
          `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
          `created` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          `note_id` INT UNSIGNED NOT NULL COMMENT 'Notification ID - foreign key to original notification record.',
          `acc_id` INT UNSIGNED NOT NULL COMMENT 'Organisation account ID - foreign key to an Account record (most likely a Repository account, but could be Publisher account).',
          `filename` VARCHAR(100) CHARACTER SET 'ascii' COLLATE 'ascii_bin'  NOT NULL,
          `source` VARCHAR(45) CHARACTER SET 'ascii' COLLATE 'ascii_bin' NOT NULL COMMENT 'The location that the content was delivered from.',
          PRIMARY KEY (`id`))
        ENGINE = InnoDB
        DEFAULT CHARACTER SET = utf8mb3
        COMMENT = 'Records retrieval of content (e.g. zip package files or PDF files) from Routers (temporary) store.';
        """,

    "doi_register":
        """
        CREATE TABLE IF NOT EXISTS `doi_register` (
          `id` VARCHAR(255) NOT NULL COMMENT 'The id is the article DOI reference.',
          `created` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          `updated` DATETIME NOT NULL COMMENT 'Value is always set deliberately, not automatically by MySQL.',
          `category` CHAR(3) NULL DEFAULT NULL COMMENT 'Type of resource.  Value is between 1 and 3 characters. First character one of: J-journal, B-book, C-conference, R-report, P-pre-print, V-review, O-other. Second & third characters, if present, further refine the categorisation.',
          `has_pdf` TINYINT NULL DEFAULT NULL COMMENT 'Indicates if text (e.g. PDF) supplied or not.  Value 1 = Full-text, NULL = Metadata only (no full text).',
          `routed_live` TINYINT NULL DEFAULT NULL COMMENT 'Indicates DOI has been sent to at least 1 live repository.  Value 1 = DOI sent to at least 1 Live repository, 0 or NULL = DOI sent only to Test repos.',
          `json` VARCHAR(3000) CHARACTER SET 'ascii' COLLATE 'ascii_bin' NULL DEFAULT NULL,
          PRIMARY KEY (`id`),
          INDEX `created_updated` (`created` ASC, `updated` ASC) VISIBLE
        )
        ENGINE = InnoDB
        DEFAULT CHARACTER SET = utf8mb3
        COMMENT = 'Stores information on which repositories have received a particular article DOI.';
        """,

    "match_provenance":
        """
        CREATE TABLE IF NOT EXISTS `match_provenance` (
          `note_id` INT UNSIGNED NOT NULL COMMENT 'This is the ID of the Notification.  It could be set as FK on `notification.id`, but not much point.',
          `repo_id` INT UNSIGNED NOT NULL COMMENT 'This is Repository Account ID/ It could be set as FK on `account.id` but not much point...',
          `created` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          `json` VARCHAR(20000) NULL DEFAULT NULL COMMENT 'Although data structures are usually small, some publishers provide a single affiliation string containing all authors data concatenated.',
          PRIMARY KEY (`note_id`, `repo_id`)
        )
        ENGINE = InnoDB
        DEFAULT CHARACTER SET = utf8mb3
        COMMENT = 'Stores \"match provenance\" - stores the information that caused a particular notification to be matched to a particular repository account.';
        """,

    "metrics":
        """
        CREATE TABLE IF NOT EXISTS `metrics` (
          `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
          `start` DATETIME NOT NULL COMMENT 'Time (UTC) that the process started.' ,
          `duration` DECIMAL(8,3) NOT NULL COMMENT 'Duration in Seconds to 3 decimal places (nnnnn.nnn) for process to complete.',
          `server` VARCHAR(45) CHARACTER SET 'ascii' COLLATE 'ascii_bin' DEFAULT NULL COMMENT 'Server on which process runs.',
          `proc_name` VARCHAR(80) CHARACTER SET 'ascii' COLLATE 'ascii_bin' NOT NULL COMMENT 'Process name.',
          `measure` VARCHAR(80) CHARACTER SET 'ascii' COLLATE 'ascii_bin' DEFAULT NULL COMMENT 'What is being measured (counted).',
          `count` MEDIUMINT UNSIGNED DEFAULT NULL COMMENT 'Count.',
          `json` VARCHAR(2000) CHARACTER SET 'utf8mb4' COLLATE 'utf8mb4_0900_ai_ci' DEFAULT NULL COMMENT 'Other data.',
          PRIMARY KEY (`id`),
          INDEX `count_procname` (`count` ASC, `proc_name` ASC) VISIBLE,
          INDEX `count_start_procname` (`count` ASC, `start` DESC, `proc_name` ASC) VISIBLE
        )
        ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 
        COMMENT='Table stores processing metrics';
        """,

    "harvested_unrouted":
        """
        CREATE TABLE IF NOT EXISTS `harvested_unrouted` (
          `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
          `created` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          `json` MEDIUMTEXT NULL DEFAULT NULL COMMENT 'Medium text holds 16MB.  Varchar holds upto 64KB, but that may not be sufficient for some (physics) notifications with 3000+ authors.',
          PRIMARY KEY (`id`))
        ENGINE = InnoDB
        DEFAULT CHARACTER SET = utf8mb3
        COMMENT = 'Harvested Unrouted Notification metadata';
    """,

    "notification":
        """
        CREATE TABLE IF NOT EXISTS `notification` (
          `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
          `created` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          `type` CHAR(1) CHARACTER SET 'ascii' COLLATE 'ascii_bin' NOT NULL COMMENT 'Notification type: "U" --> Unrouted ; "R" --> Routed',
          `analysis_date` DATETIME NULL DEFAULT NULL COMMENT 'Will be NULL for UnroutedNotification.',
          `doi` VARCHAR(255) NULL DEFAULT NULL COMMENT 'Article DOI.  Will be NULL for UnroutedNotification.',
          `prov_id` INT UNSIGNED NULL DEFAULT NULL COMMENT 'Publisher Provider (Publisher account record) ID.  Will be NULL for UnroutedNotification.',
          `prov_harv_id` INT UNSIGNED NULL DEFAULT NULL COMMENT 'Harvester Provider (Harvester web-service record) ID.  Will be NULL for UnroutedNotification.',
          `prov_agent` VARCHAR(45) CHARACTER SET 'ascii' COLLATE 'ascii_bin' NULL DEFAULT NULL COMMENT 'Provider agent.  Will be NULL for UnroutedNotification.',
          `prov_route` VARCHAR(5) CHARACTER SET 'ascii' COLLATE 'ascii_bin' NULL DEFAULT NULL COMMENT 'Provider route ("ftp", "api", "sword" or "harv").  Will be NULL for UnroutedNotification.',
          `prov_rank` TINYINT NULL DEFAULT NULL COMMENT 'Provider rank - 1 to 3.  Will be NULL for UnroutedNotification.',
          `repositories` VARCHAR(2000) CHARACTER SET 'ascii' COLLATE 'ascii_bin' NULL DEFAULT NULL COMMENT 'List of repositories that have been matched to this notification. String of Repository IDs, separated by "|" character.   Will always be NULL for UnroutedNotification.',
          `pkg_format` VARCHAR(100) CHARACTER SET 'ascii' COLLATE 'ascii_bin' NULL DEFAULT NULL COMMENT 'Packaging format - extracted from JSON as used when full json NOT needed (when retrieving file content via API).  Will be NULL for UnroutedNotification.',
          `links_json` VARCHAR(8000) CHARACTER SET 'ascii' COLLATE 'ascii_bin' NULL DEFAULT NULL COMMENT 'Links json array of dicts - extracted from JSON as is used when full json NOT needed (when retrieving file content via API).  Substantial size because zip files have been encountered with large numbers of PDF files which, for Eprints repositories, are unpacked resulting in many links.  Will be NULL for UnroutedNotification.',
          `metrics_val` VARCHAR(500) CHARACTER SET 'ascii' COLLATE 'ascii_bin' NULL DEFAULT NULL COMMENT 'Specially compressed notification metrics val dict. Will be NULL for UnroutedNotification.',
          `json` MEDIUMTEXT NULL DEFAULT NULL COMMENT 'Medium text holds 16MB.  Varchar holds upto 64KB, but that may not be sufficient for some (physics) notifications with 3000+ authors.',
          PRIMARY KEY (`id`),
          INDEX `type` (`type` ASC) VISIBLE,
          INDEX `analysis_date_prov_id` (`analysis_date` ASC, `prov_id` ASC) VISIBLE,
          INDEX `prov_harv_id` (`prov_harv_id` ASC) VISIBLE,
          INDEX `prov_id` (`prov_id` ASC) VISIBLE)
        ENGINE = InnoDB
        DEFAULT CHARACTER SET = utf8mb3
        COMMENT = 'Notification metadata';
        """,

    "notification_account":
        """
        CREATE TABLE IF NOT EXISTS `notification_account` (
          `id_note` INT UNSIGNED NOT NULL COMMENT 'The ID of the notification (notification.id).',
          `id_acc` INT UNSIGNED NOT NULL COMMENT 'The ID of the account (account.id) that a particular notification is routed to.',
          PRIMARY KEY (`id_note`, `id_acc`),
          INDEX `id_acc` (`id_acc` ASC) VISIBLE)
        ENGINE = InnoDB
        DEFAULT CHARACTER SET = utf8mb3
        COMMENT = 'Maps notifications to the accounts they have been matched to.  Entries in this table are NOT saved long-term, but are deleted when corresponding notifications are deleted.';
        """,

    "org_identifiers":
        """
        CREATE TABLE IF NOT EXISTS `org_identifiers` (
          `type` VARCHAR(10) CHARACTER SET 'ascii' COLLATE 'ascii_bin' NOT NULL,
          `value` VARCHAR(45) CHARACTER SET 'ascii' COLLATE 'ascii_bin' NOT NULL,
          `name` VARCHAR(200) NOT NULL,
          PRIMARY KEY (`type`, `value`))
        ENGINE = InnoDB
        DEFAULT CHARACTER SET = utf8mb3
        COMMENT = 'Stores organisation Identifiers - lookup table - iniitally Jisc and CORE identifiers for repositories.';
        """,

    "pub_deposit":
        """
        CREATE TABLE IF NOT EXISTS `pub_deposit` (
          `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
          `created` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          `updated` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          `pub_id` INT UNSIGNED NOT NULL,
          `note_id` INT UNSIGNED NULL DEFAULT NULL,
          `type` CHAR(1) CHARACTER SET 'ascii' COLLATE 'ascii_bin' NOT NULL COMMENT ' ',
          `matched` TINYINT NULL DEFAULT NULL COMMENT 'Boolean (0/1) - whether publisher submission was matched to any repository (Live or Test)',
          `matched_live` TINYINT NULL DEFAULT NULL COMMENT 'Boolean (0/1) - whether publisher submission was matched to any Live repository',
          `successful` TINYINT NULL DEFAULT NULL COMMENT 'Boolean (0/1) - whether publisher submission was successfully processed',
          `name` VARCHAR(100) NULL DEFAULT NULL COMMENT 'File or directory name',
          `error` VARCHAR(2000) NULL DEFAULT NULL,
          `sword_in_progress` TINYINT NULL DEFAULT NULL,
          `err_emailed` TINYINT NULL DEFAULT NULL COMMENT 'Indicates if error included in an email.',
          PRIMARY KEY (`id`),
          INDEX `pubid_created` (`pub_id` ASC, `created` ASC) VISIBLE,
          INDEX `note_id` (`note_id` ASC) VISIBLE,
          INDEX `created` (`created` ASC) VISIBLE)
        ENGINE = InnoDB
        DEFAULT CHARACTER SET = utf8mb3
        COMMENT = 'Stores a record of each publisher deposit';
        """,

    "pub_test":
        """
        CREATE TABLE IF NOT EXISTS `pub_test` (
          `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
          `created` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          `pub_id` INT UNSIGNED NOT NULL,
          `json_comp` MEDIUMTEXT NULL DEFAULT NULL COMMENT 'Compressed notification JSON structure.',
          `json` MEDIUMTEXT NULL DEFAULT NULL COMMENT 'MEDIUMTEXT because have encountered situations where `json` exceeded the maximum size allowed for varchar: VARCHAR(8000).',
          PRIMARY KEY (`id`),
          INDEX `pub_id` (`pub_id` ASC) VISIBLE)
        ENGINE = InnoDB
        DEFAULT CHARACTER SET = utf8mb3
        COMMENT = 'Stores results of each publisher automated test.';
        """,

    "sword_deposit":
        """
        CREATE TABLE IF NOT EXISTS `sword_deposit` (
          `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
          `deposit_date` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Date of deposit.',
          `note_id` INT UNSIGNED NOT NULL COMMENT 'Notification ID',
          `repo_id` INT UNSIGNED NOT NULL COMMENT 'Repository ID',
          `metadata_status` TINYINT NULL DEFAULT NULL COMMENT '0 - FAILED; 1 - DEPOSITED',
          `content_status` TINYINT NULL DEFAULT NULL COMMENT '0 - FAILED; 1 - DEPOSITED',
          `completed_status` TINYINT NULL DEFAULT NULL COMMENT '0 - FAILED; 1 - DEPOSITED',
          `error_message` VARCHAR(10000) NULL DEFAULT NULL,
          `doi` VARCHAR(255) NULL DEFAULT NULL,
          `edit_iri` VARCHAR(1000) NULL DEFAULT NULL,
          `err_emailed` TINYINT NULL DEFAULT NULL COMMENT 'Indicates if error included in an email.',
          PRIMARY KEY (`id`),
          INDEX `deposit_date` (`deposit_date` ASC) VISIBLE,
          INDEX `repoid_depositdate` (`repo_id` ASC, `deposit_date` ASC) VISIBLE,
          INDEX `noteid_repoid_metastatus` (`note_id` ASC, `repo_id` ASC, `metadata_status` ASC) VISIBLE,
          INDEX `repoid_doi_metastatus` (`repo_id` ASC, `doi` ASC, `metadata_status` ASC) VISIBLE)
        ENGINE = InnoDB
        DEFAULT CHARACTER SET = utf8mb3
        COMMENT = 'Records details for each notification deposit attempted via SWORD.';
        """,

    "h_webservice":
        """
        CREATE TABLE IF NOT EXISTS `h_webservice` (
          `id` INT NOT NULL AUTO_INCREMENT,
          `updated` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
          `name` VARCHAR(100) CHARACTER SET 'ascii' COLLATE 'ascii_bin' NOT NULL,
          `url` VARCHAR(500) CHARACTER SET 'ascii' COLLATE 'ascii_bin' NOT NULL,
          `query` VARCHAR(1000) CHARACTER SET 'ascii' COLLATE 'ascii_bin' NOT NULL,
          `frequency` VARCHAR(10) CHARACTER SET 'ascii' COLLATE 'ascii_bin' NOT NULL,
          `active` TINYINT NULL DEFAULT NULL,
          `email` VARCHAR(100) CHARACTER SET 'ascii' COLLATE 'ascii_bin' NULL DEFAULT NULL,
          `engine` VARCHAR(50) CHARACTER SET 'ascii' COLLATE 'ascii_bin' NULL DEFAULT NULL,
          `wait_window` SMALLINT NULL DEFAULT NULL,
          `publisher` TINYINT NULL DEFAULT NULL,
          `end_date` CHAR(10) CHARACTER SET 'ascii' COLLATE 'ascii_bin' NULL DEFAULT NULL COMMENT 'YYYY-MM-DD stored as string rather than datetime because internally Harvester does not use UTC format, so this easier.',
          `live_date` CHAR(10) CHARACTER SET 'ascii' COLLATE 'ascii_bin' NULL DEFAULT NULL COMMENT 'YYYY-MM-DD stored as string rather than datetime because internally Harvester does not use UTC format, so this easier.',
          `notes` VARCHAR(3000) NULL DEFAULT NULL COMMENT 'Notes to display on webservice screen.',
          `auto_enable` SMALLINT NULL DEFAULT NULL COMMENT 'Whether harvester webservice should be automatically enabled for new Repo accounts or not.',
          PRIMARY KEY (`id`),
          UNIQUE INDEX `name_UNIQUE` (`name` ASC) VISIBLE,
          INDEX `publisher` (`publisher` ASC) VISIBLE,
          INDEX `live_date` (`live_date` ASC) VISIBLE)
        ENGINE = InnoDB
        DEFAULT CHARACTER SET = utf8mb3
        COMMENT = 'Harvester web-service definitions.';
        """,

    "h_errors":
        """
        CREATE TABLE IF NOT EXISTS `h_errors` (
          `id` INT NOT NULL AUTO_INCREMENT,
          `created` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          `ws_id` INT NOT NULL,
          `hist_id` INT NULL DEFAULT NULL,
          `error` VARCHAR(10000) NULL DEFAULT NULL,
          `document` MEDIUMTEXT NULL DEFAULT NULL,
          `url` VARCHAR(500) NULL DEFAULT NULL,
          PRIMARY KEY (`id`),
          INDEX `hist_id_idx` (`hist_id` ASC) VISIBLE,
          INDEX `ws_id_idx` (`ws_id` ASC) VISIBLE,
          INDEX `created` (`created` ASC) VISIBLE)
        ENGINE = InnoDB
        DEFAULT CHARACTER SET = utf8mb3;
        """,

    "h_history":
        """
        CREATE TABLE IF NOT EXISTS `h_history` (
          `id` INT NOT NULL AUTO_INCREMENT,
          `created` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          `ws_id` INT NOT NULL COMMENT 'Foreign key to web-service record that this history item is associated with.',
          `query` VARCHAR(1000) CHARACTER SET 'ascii' COLLATE 'ascii_bin' NULL DEFAULT NULL,
          `url` VARCHAR(500) CHARACTER SET 'ascii' COLLATE 'ascii_bin' NULL DEFAULT NULL,
          `start_date` CHAR(10) CHARACTER SET 'ascii' COLLATE 'ascii_bin' NULL DEFAULT NULL COMMENT 'YYYY-MM-DD stored as string rather than datetime because internally Harvester does not use UTC format, so this easier.',
          `end_date` CHAR(10) CHARACTER SET 'ascii' COLLATE 'ascii_bin' NULL DEFAULT NULL COMMENT 'YYYY-MM-DD stored as string rather than datetime because internally Harvester does not use UTC format, so this easier.',
          `num_received` INT NULL DEFAULT NULL,
          `num_sent` INT NULL DEFAULT NULL,
          `num_errors` INT NULL DEFAULT NULL,
          PRIMARY KEY (`id`),
          INDEX `ws_fk` (`ws_id` ASC) VISIBLE,
          INDEX `created` (`created` ASC) VISIBLE,
          INDEX `start_date` (`start_date` ASC) VISIBLE)
        ENGINE = InnoDB
        DEFAULT CHARACTER SET = utf8mb3;
        """,

    "job":
        """
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
        """
}

JPER_REPORTS_TABLES = {
    "monthly_harvester_stats":
        """
        CREATE TABLE IF NOT EXISTS `monthly_harvester_stats` (
          `year_month_date` DATE NOT NULL COMMENT 'Year-Month-01  (the first day of the month for which statistics apply).',
          `acc_id` INT UNSIGNED NOT NULL COMMENT 'Foreign key to Harvester Webservice record.',
          `received` MEDIUMINT UNSIGNED NULL DEFAULT NULL COMMENT 'Number of notifications received.',
          `matched` MEDIUMINT UNSIGNED NULL DEFAULT NULL COMMENT 'Number of notifications matched to LIVE repository accounts.',
          PRIMARY KEY (`year_month_date`, `acc_id`))
        ENGINE = InnoDB
        DEFAULT CHARACTER SET = utf8mb3
        COMMENT = 'Monthly statistics for harvesters recording the number of notifications received and the number matched to LIVE repository accounts.';
        """,

    "monthly_institution_stats":
        """
        CREATE TABLE IF NOT EXISTS `monthly_institution_stats` (
          `year_month_date` DATE NOT NULL COMMENT 'Year-Month-01  (the first day of the month for which statistics apply).',
          `type` CHAR(1) CHARACTER SET 'ascii' COLLATE 'ascii_bin' NOT NULL COMMENT 'Type is \"L\" for Live or \"T\" for Test account.',
          `acc_id` INT UNSIGNED NOT NULL COMMENT 'Foreign key to Account record.',
          `metadata_only` SMALLINT UNSIGNED NULL DEFAULT NULL COMMENT 'Number of notifications received.',
          `with_content` SMALLINT UNSIGNED NULL DEFAULT NULL COMMENT 'Number of notifications matched.',
          PRIMARY KEY (`type`, `year_month_date`, `acc_id`))
        ENGINE = InnoDB
        DEFAULT CHARACTER SET = utf8mb3
        COMMENT = 'Monthly statistics for Live and Test repositories: recording the number of notifications received and the number matched.';
        """,

    "monthly_publisher_stats":
        """
        CREATE TABLE IF NOT EXISTS `monthly_publisher_stats` (
          `year_month_date` DATE NOT NULL COMMENT 'Year-Month-01  (the first day of the month for which statistics apply).',
          `acc_id` INT UNSIGNED NOT NULL COMMENT 'Foreign key to Account record.',
          `received` MEDIUMINT UNSIGNED NULL DEFAULT NULL COMMENT 'Number of notifications received.',
          `matched` MEDIUMINT UNSIGNED NULL DEFAULT NULL COMMENT 'Number of notifications matched.',
          PRIMARY KEY (`year_month_date`, `acc_id`))
        ENGINE = InnoDB
        DEFAULT CHARACTER SET = utf8mb3
        COMMENT = 'Monthly statistics for publishers: recording the number of notifications received and the number matched.';
        """,
}
