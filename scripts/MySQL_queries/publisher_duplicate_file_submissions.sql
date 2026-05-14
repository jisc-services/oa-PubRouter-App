-- Queries to count Publisher's Duplicate file submissions within past 90 days


SELECT
	a.org_name AS Publisher,
    COUNT(pd.id) AS `Duplicate count`,
    n.doi as DOI,
    GROUP_CONCAT(DISTINCT pd.name ORDER BY 1 SEPARATOR ', ') AS `File names`,
    GROUP_CONCAT(DATE(pd.created) ORDER BY 1 SEPARATOR ', ') AS `Deposit dates`,
    GROUP_CONCAT(DISTINCT (SELECT GROUP_CONCAT(DISTINCT aa.org_name SEPARATOR ', ' ) FROM notification_account na JOIN account aa ON aa.id = na.id_acc WHERE na.id_note = pd.note_id) SEPARATOR ', ') AS Repositories,
    GROUP_CONCAT(pd.note_id ORDER BY 1 SEPARATOR ', ') AS `Note IDs`,
    REPLACE(GROUP_CONCAT(distinct REGEXP_REPLACE(n.metrics_json, ',"p_count".*', '}', 122) ORDER BY 1 SEPARATOR ', '), '"', '\'') AS `Metrics`
FROM pub_deposit pd
JOIN notification n ON n.id = pd.note_id
JOIN account a ON a.id = pd.pub_id
WHERE pd.matched_live = 1
AND DATE(pd.created) > DATE_SUB(CURDATE(), INTERVAL 90 DAY)
GROUP BY n.doi
HAVING `Duplicate count` > 1
ORDER BY 2 DESC     -- Count
;



-- INITIAL VERSION BELOW - FOR FTP SUBMISSIONS ONLY --

-- It assumes that filenames (pd.name) are unique to particular DOIs
SELECT 
	a.org_name AS Publisher, 
    pd.name AS `File name`, 
    COUNT(pd.id) AS `Duplicate count`, 
    GROUP_CONCAT(DATE(pd.created) ORDER BY 1 SEPARATOR ', ') AS `Deposit dates`, 
    GROUP_CONCAT(DISTINCT (SELECT n.doi FROM notification n WHERE n.id = pd.note_id ) SEPARATOR ', ') AS DOI, 
    GROUP_CONCAT(DISTINCT (SELECT GROUP_CONCAT(DISTINCT aa.org_name SEPARATOR ', ' ) FROM notification_account na JOIN account aa ON aa.id = na.id_acc WHERE na.id_note = pd.note_id) SEPARATOR ', ') AS Repositories,
    GROUP_CONCAT(pd.note_id ORDER BY 1 SEPARATOR ', ') AS `Note IDs`
FROM pub_deposit pd
JOIN account a ON a.id = pd.pub_id
WHERE pd.matched_live = 1
AND DATE(pd.created) > DATE_SUB(CURDATE(), INTERVAL 90 DAY)
AND pd.type = 'F'   -- File from API always have same pd.name value, so ALL appear to be duplicates
GROUP BY pd.name
HAVING `Duplicate count` > 1
ORDER BY 1, 4 DESC
-- order by name desc
;


SELECT 
	a.org_name AS Publisher, 
    pd.name AS `File name`, 
    COUNT(pd.id) AS `Duplicate count`, 
    GROUP_CONCAT(DATE(pd.created) ORDER BY 1 SEPARATOR ', ') AS `Deposit dates`, 
    GROUP_CONCAT(DISTINCT (SELECT n.doi FROM notification n WHERE n.id = pd.note_id ) SEPARATOR ', ') AS DOI, 
    GROUP_CONCAT(DISTINCT (SELECT GROUP_CONCAT(DISTINCT aa.org_name SEPARATOR ', ' ) FROM notification_account na JOIN account aa ON aa.id = na.id_acc WHERE na.id_note = pd.note_id) SEPARATOR ', ') AS Repositories,
    GROUP_CONCAT(pd.note_id ORDER BY 1 SEPARATOR ', ') AS `Note IDs`
FROM pub_deposit pd
JOIN account a ON a.id = pd.pub_id
WHERE pd.matched_live = 1
AND DATE(pd.created) > DATE_SUB(CURDATE(), INTERVAL 90 DAY)
AND pd.type = 'F'
GROUP BY pd.name
HAVING `Duplicate count` > 1
ORDER BY 1, 4 DESC
-- order by name desc
INTO OUTFILE 'C:/tmp/test.csv' 
FIELDS ENCLOSED BY '"' 
TERMINATED BY ';' 
ESCAPED BY '"' 
LINES TERMINATED BY '\r\n';
;


-- SAFETY -- new script for report
SELECT
	GROUP_CONCAT(DISTINCT a.org_name) AS Publisher,
    COUNT(pd.id) AS `Duplicate count`,
    n.doi as DOI,
    GROUP_CONCAT(DISTINCT pd.name ORDER BY 1 SEPARATOR ', ') AS `File names`,
    GROUP_CONCAT(DATE(pd.created) ORDER BY 1 SEPARATOR ', ') AS `Deposit dates`,
    GROUP_CONCAT(DISTINCT (SELECT GROUP_CONCAT(DISTINCT aa.org_name SEPARATOR ', ' ) FROM notification_account na JOIN account aa ON aa.id = na.id_acc WHERE na.id_note = pd.note_id) SEPARATOR ', ') AS Repositories,
    GROUP_CONCAT(pd.note_id ORDER BY 1 SEPARATOR ', ') AS `Note IDs`,
    REPLACE(GROUP_CONCAT(distinct n.metrics_val ORDER BY 1 SEPARATOR ', '), '"', '\'') AS `Metrics`
FROM pub_deposit pd
JOIN notification n ON n.id = pd.note_id
JOIN account a ON a.id = pd.pub_id
WHERE pd.matched_live = 1
AND DATE(pd.created) > DATE_SUB(CURDATE(), INTERVAL 90 DAY)
GROUP BY n.doi
HAVING `Duplicate count` > 1
ORDER BY 2 DESC     -- Count
;

