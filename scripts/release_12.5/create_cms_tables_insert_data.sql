-- MySQL dump 10.13  Distrib 8.0.30, for Win64 (x86_64)
--
-- Host: localhost    Database: jper
-- ------------------------------------------------------
-- Server version	8.0.23

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `cms_ctl`
--

DROP TABLE IF EXISTS `cms_ctl`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `cms_ctl` (
  `cms_type` varchar(15) NOT NULL COMMENT 'Keyword name by which type of content is known - should NOT contain spaces.',
  `updated` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `brief_desc` varchar(80) NOT NULL COMMENT 'Brief description of content type, e.g. for drop-down list.',
  `json` varchar(10000) DEFAULT NULL COMMENT 'Not sure if this will be needed.',
  PRIMARY KEY (`cms_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Control table managed content - contains details of each type of managed content.';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `cms_ctl`
--

LOCK TABLES `cms_ctl` WRITE;
/*!40000 ALTER TABLE `cms_ctl` DISABLE KEYS */;
INSERT INTO `cms_ctl` VALUES ('3_pubs','2022-10-12 08:31:00','Latest three publishers','{\"fields\":[{\"field\":\"pubs\",\"label\":\"3 most recent publishers\",\"placeholder\":\"Three entries, each like: &lt;dd&gt;Publisher name&lt;/dd&gt;\",\"sample\":\"<dd>Most recent publisher</dd><dd>Publisher</dd><dd>Third oldest publisher</dd>\",\"rows\":4}],\"full_desc\":\"List of 3 most recent publishers for display on <i>Router home page</i>. NOTE: Only <b>one</b> entry should be <b>Live</b> at any time.\",\"multi\":false,\"preview_wrapper\":\"<dl><div class=\\\"preview\\\"></div></dl>\",\"page_link\":\"/\",\"template\":\"{pubs}\",\"title\":\"\'latest 3 publishers\'\"}'),('pub_provider','2022-10-12 08:31:00','Publisher content providers','{\"fields\":[{\"field\":\"pub\",\"label\":\"Publisher name\",\"placeholder\":\"Publisher\'s name as it is to appear in left column of table.  E.g. <a target=&quot;_blank&quot; href=&quot;https://www.publisher/website/&quot;>Publisher Name</a>\",\"rows\":2,\"sample\":\"<a target=\\\"_blank\\\" href=\\\"https://www.publisher/website/\\\">Publisher Name</a>\"},{\"field\":\"desc\",\"label\":\"What is provided\",\"placeholder\":\"Details to appear in right column of table (including necessary HTML tags).\",\"rows\":6,\"sample\":\"Some text<br><br>More text<ul><li>Bullet 1</li><li>Bullet 2.</li></ul>\"}],\"full_desc\":\"For display on the <i>Current content providers</i> page - Publisher name (linked to their website), plus the content they provide & when.\",\"multi\":true,\"page_link\":\"/about/providerlist/\",\"preview_wrapper\":\"<div><table class=\\\"std-txt\\\"><tbody class=\\\"preview\\\"></tbody></table></div>\",\"template\":\"<tr><td>{pub}</td><td>{desc}</td></tr>\",\"title\":\"\'publisher content provider\'\"}');
/*!40000 ALTER TABLE `cms_ctl` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `cms_html`
--

DROP TABLE IF EXISTS `cms_html`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `cms_html` (
  `id` int unsigned NOT NULL AUTO_INCREMENT,
  `created` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `cms_type` varchar(15) NOT NULL COMMENT 'Type of content - Foreign Key to entry in content_mgt_ctl table',
  `status` char(1) DEFAULT NULL COMMENT 'Status, possible values:\nN - New (not Live)\nL - Live\nD - Deleted\nS - Superseded',
  `sort_value` varchar(40) DEFAULT '' COMMENT 'Value on which to sort records of same content)type to ensure they appear in required order.',
  `json` varchar(10000) DEFAULT NULL COMMENT 'JSON structure will contain the actual content for each of the fields specified in content_mgt_ctl table for this particular content_type.',
  PRIMARY KEY (`id`),
  KEY `ctype_status` (`cms_type`,`status`)
) ENGINE=InnoDB AUTO_INCREMENT=21 DEFAULT CHARSET=utf8mb4 COMMENT='Contains managed content (user editable) for display on HTML pages.';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `cms_html`
--

LOCK TABLES `cms_html` WRITE;
/*!40000 ALTER TABLE `cms_html` DISABLE KEYS */;
INSERT INTO `cms_html` VALUES (1,'2022-09-27 19:06:05','2022-10-12 09:03:41','pub_provider','L','Elife','{\"fields\":{\"pub\":\"<a target=\\\"_blank\\\" href=\\\"https://elifesciences.org/\\\">eLife</a>\",\"desc\":\"Metadata, full text (VoR) as PDF and XML, additional files associated with the article (illustrations, video etc) - daily, upon publication. No embargo.\"}}'),(2,'2022-09-27 20:26:45','2022-10-12 09:26:02','pub_provider','L','Elsevier','{\"fields\":{\"desc\":\"Metadata only.</br></br>\\nFor articles hosted on the <a target=\\\"_blank\\\" href=\\\"https://www.sciencedirect.com/\\\">Science Direct</a> platform:</br></br>\\n<strong>Within four weeks of acceptance</strong></br>\\nPreliminary metadata including article acceptance date (but without volume, issue, page details or embargo end date). An embargo applies (to full text of the article described) unless the metadata explicitly indicates the contrary. (The embargo end date will follow upon publication, as below.)</br>\\n- daily, upon availability of initial minimal metadata set.</br></br>\\n<strong>Upon publication</strong></br>\\nCompleted metadata including volume, issue, page numbers, embargo end date (as applicable to UK-authored articles), post-embargo licence, name of the article version (AM or VoR) to which the licensing metadata refers - daily, upon publication of the version of record in a journal issue.</br></br>\\n<strong>Embargo exception for UK REF</strong></br>\\nThe metadata will normally describe the embargo period that applies to UK researchers funded by UKRI, Wellcome Trust or who are complying with the HEFCE REF policy, where applicable. In rare cases in which this may not be reflected as expected, please refer to Elsevier\\u2019s <a target=\\\"_blank\\\" href=\\\"https://www.elsevier.com/__data/assets/pdf_file/0011/78473/UK-Embargo-Periods.pdf\\\">UK embargo list</a> for details of how to amend manually.</br>\\n\",\"pub\":\"<a target=\\\"_blank\\\" href=\\\"https://www.elsevier.com/\\\">Elsevier</a>\"}}'),(3,'2022-09-27 20:28:23','2022-10-12 09:26:02','pub_provider','L','Emerald','{\"fields\":{\"desc\":\"For articles whose corresponding author is affiliated to an institution that subscribes to Emerald\\u2019s journals via the Jisc-negotiated agreement:</br></br>\\nMetadata, full text (AM) as PDF \\u2013 in regular batches soon after acceptance.</br></br>\\nMetadata includes details of the article\\u2019s CC BY licence. No embargo.\\n\",\"pub\":\"<a target=\\\"_blank\\\" href=\\\"https://www.emeraldgrouppublishing.com/\\\">Emerald</a>\"}}'),(4,'2022-09-27 20:28:56','2022-10-12 09:26:02','pub_provider','L','Frontiers','{\"fields\":{\"desc\":\"Metadata, full text (VoR) as PDF and XML, additional files associated with the article (illustrations, video etc) \\u2013 daily, upon publication. No embargo.\",\"pub\":\"<a target=\\\"_blank\\\" href=\\\"https://www.frontiersin.org/\\\">Frontiers</a>\"}}'),(5,'2022-09-27 20:30:01','2022-10-12 09:26:02','pub_provider','L','Future Science Group','{\"fields\":{\"desc\":\"Two deliveries:</br></br>\\n<strong>Upon \\u201cahead of print\\u201d publication (where applicable) before inclusion in a journal issue</strong></br>\\nMetadata (without volume, issue and page details) plus full text (\\u201cahead of print\\u201d VoR) as PDF \\u2013 daily.</br></br>\\n<strong>Upon publication in a journal issue</strong></br>\\nCompleted metadata plus full text (finalised VoR) as PDF \\u2013 daily.</br></br>\\nSubscription content is subject to a 12-month embargo from the date of initial publication. The embargo end date for each article is indicated in the metadata.</br></br>\\nGold OA articles are also included as above, but with no embargo.\\n\",\"pub\":\"Future Science Group</br></br>\\n\\tIncluding:</br></br>\\n\\t<a target=\\\"_blank\\\" href=\\\"https://www.future-science.com/\\\">Future Science</a></br>\\n\\t<a target=\\\"_blank\\\" href=\\\"https://www.futuremedicine.com/\\\">Future Medicine</a></br>\\n\\t<a target=\\\"_blank\\\" href=\\\"https://www.future-science.com/\\\">Newlands Press</a>\\n\"}}'),(6,'2022-09-27 20:31:23','2022-10-12 09:26:02','pub_provider','L','IOP','{\"fields\":{\"desc\":\"For gold open access content from their hybrid and wholly OA journals:</br></br>Metadata, full text (VoR) as PDF \\u2013 daily upon publication. No embargo.</br></br>(IOP Publishing intends to supply AMs of subscription content from a future date.)\",\"pub\":\"<a target=\\\"_blank\\\" href=\\\"https://ioppublishing.org/\\\">IOP Publishing</a>\"}}'),(7,'2022-09-27 20:31:56','2022-10-12 09:26:02','pub_provider','L','MDPI','{\"fields\":{\"desc\":\"Metadata, full text (VoR) as PDF and XML, additional files associated with the article (illustrations, video etc) \\u2013 daily, upon publication. No embargo.\",\"pub\":\"<a target=\\\"_blank\\\" href=\\\"https://www.mdpi.com/\\\">MDPI</a>\"}}'),(8,'2022-09-27 20:32:44','2022-10-12 09:26:02','pub_provider','L','National Academy of Sciences','{\"fields\":{\"desc\":\"For open access content published in <i>Proceedings of the National Academy of Sciences of the United States of America</i> (<a href=\\\"https://www.pnas.org/\\\">PNAS</a>): <br><br>Metadata, full text (VoR) as PDF \\u2013 daily; for an initial period, upon publication of the journal issue; thereafter (from early 2022) upon first online publication of the VoR. <br><br>Metadata includes details of the article\\u2019s creative commons licence. No embargo.\",\"pub\":\"<a target=\\\"_blank\\\" href=\\\"http://www.nasonline.org/\\\">National Academy of Sciences</a>\"}}'),(9,'2022-09-27 20:33:38','2022-10-12 09:26:02','pub_provider','L','PLOS ','{\"fields\":{\"desc\":\"Metadata, full text (VoR) as PDF and XML, additional files associated with the article (illustrations, video etc) - daily, upon publication. No embargo.\",\"pub\":\"<a target=\\\"_blank\\\" href=\\\"https://www.plos.org/\\\">PLOS (Public Library of Science)</a>\"}}'),(10,'2022-09-27 20:34:18','2022-10-12 09:26:02','pub_provider','L','SAGE Publishing','{\"fields\":{\"desc\":\"For gold open access articles from their hybrid and wholly OA journals:\\n<br><br>Metadata, full text (VoR) as PDF \\u2013 daily upon publication. No embargo.\",\"pub\":\"<a target=\\\"_blank\\\" href=\\\"https://sagepub.com/\\\">SAGE Publishing</a>\"}}'),(11,'2022-09-27 20:35:09','2022-10-12 09:26:02','pub_provider','L','Springer Nature','{\"fields\":{\"desc\":\"Metadata, full text (VoR) as PDF and XML - daily, upon publication, or upon availability of \\\"online early\\\" version. There are no embargos on this content.\\n<br>\\nIncludes:\\n<ul>\\n\\t<li>For journals in the Springer imprint, UK co-authored articles that have been made gold OA under the Springer Compact agreement.</li>\\n\\t<li>BioMed Central OA articles</li>\\n\\t<li>SpringerOpen OA articles</li>\\n\\t<li>Articles from fully OA journals on <a target=\\\"_blank\\\" href=\\\"https://www.nature.com/\\\">nature.com</a>.</li>\\n</ul>\\n\",\"pub\":\"<a target=\\\"_blank\\\" href=\\\"http://www.springernature.com\\\">Springer Nature</a>\"}}'),(12,'2022-09-27 20:37:08','2022-10-12 09:26:02','pub_provider','L','The Company of Biologists','{\"fields\":{\"desc\":\"For gold open access content from their hybrid and wholly OA journals:\\n<br><br>Metadata, full text (VoR) as PDF, supplementary files (where available) \\u2013 daily upon publication. No embargo.\\n\",\"pub\":\"<a target=\\\"_blank\\\" href=\\\"https://www.biologists.com/\\\">The Company of Biologists</a>\"}}'),(13,'2022-09-27 20:37:37','2022-10-12 09:26:02','pub_provider','L','The Royal Society','{\"fields\":{\"desc\":\"For gold open access content from their hybrid and wholly OA journals:\\n<br><br>Metadata, full text (VoR) as PDF \\u2013daily upon publication. No embargo.\\n\",\"pub\":\"<a target=\\\"_blank\\\" href=\\\"https://royalsociety.org/journals/\\\">The Royal Society</a>\"}}'),(14,'2022-09-27 20:38:05','2022-10-12 09:26:02','pub_provider','L','Wiley','{\"fields\":{\"desc\":\"For gold open access content from their hybrid and wholly OA journals:\\n<br><br>Metadata, full text (VoR) as PDF \\u2013 daily upon first online publication of the VoR (before publication of the journal issue in most cases).\\n<br><br>Metadata includes details of the article\\u2019s creative commons licence. No embargo.\\n\",\"pub\":\"<a target=\\\"_blank\\\" href=\\\"https://onlinelibrary.wiley.com/\\\">Wiley</a>\"}}'),(15,'2022-09-27 21:39:46','2022-10-12 09:28:42','3_pubs','L','','{\"fields\":{\"pubs\":\"<dd>American Chemical Society</dd>\\n<dd>The Company of Biologists</dd>\\n<dd>Emerald</dd>\"}}'),(16,'2022-09-27 22:12:04','2022-10-12 09:26:02','pub_provider','L','American Chemical Society','{\"fields\":{\"pub\":\"<a target=\\\"_blank\\\" href=\\\"https://www.acs.org/\\\">American Chemical Society</a>\",\"desc\":\"For gold open access content from their hybrid and wholly OA journals:<br><br>\\nMetadata, full text (VoR) as PDF, any additional files associated with the article (illustrations, video etc.) \\u2013 daily upon publication. No embargo. \"}}'),(17,'2022-09-28 23:07:13','2022-10-12 09:26:02','pub_provider','L','BMJ','{\"fields\":{\"pub\":\"<a target=\\\"_blank\\\" href=\\\"http://journals.bmj.com/\\\">BMJ</a>\",\"desc\":\"For their flagship journal, The BMJ:\\n<ul>\\n  <li>Metadata, full text (VoR) as PDF and XML, for all research papers (which are all gold OA) - daily, upon publication. No embargo.</li>\\n</ul>\\n<br>\\nFor other BMJ journals:\\n<ul>\\n  <li>For gold OA papers: metadata, full text (VoR) as PDF and XML - daily, upon publication. No embargo.</li>\\n  <li>For subscription content: metadata, full text (AM) - daily, upon publication. No embargo.</li>\\n</ul>\"}}'),(18,'2022-09-29 07:57:05','2022-10-12 08:58:37','pub_provider','N','Royal Society of Chemistry','{\"fields\":{\"desc\":\"For gold open access content from their hybrid and wholly OA journals:\\n<br><br>Metadata, full text (VoR) as PDF, any additional files associated with the article (illustrations, video etc) \\u2013 daily upon first publication of the VoR, their \\u201cadvance article\\u201d stage. No embargo.\",\"pub\":\"<a target=\\\"_blank\\\" href=\\\"https://www.rsc.org/\\\">Royal Society of Chemistry</a>\"}}'),(19,'2022-10-06 17:10:45','2022-10-12 08:55:40','3_pubs','N','','{\"fields\":{\"pubs\":\"<dd>Royal Society of Chemistry</dd>\\n<dd>American Chemical Society</dd>\\n<dd>The Company of Biologists</dd>\"}}'),(20,'2022-10-11 15:53:47','2022-10-12 09:26:02','pub_provider','L','Hindawi','{\"fields\":{\"pub\":\"<a target=\\\"_blank\\\" href=\\\"https://www.hindawi.com/\\\">Hindawi</a>\",\"desc\":\"Metadata, full text (VoR) as PDF and XML, additional files associated with the article (illustrations, video etc) \\u2013 daily, upon publication. No embargo.. \"}}');
/*!40000 ALTER TABLE `cms_html` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2022-10-13 10:41:23
