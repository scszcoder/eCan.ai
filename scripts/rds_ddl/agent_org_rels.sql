CREATE TABLE `agent_org_rels` (
  `id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `agent_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `org_id` varchar(64) COLLATE utf8mb4_unicode_ci NOT NULL,
  `role` varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT 'member',
  `status` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT 'active',
  `join_date` datetime(6) DEFAULT CURRENT_TIMESTAMP(6),
  `leave_date` datetime(6) DEFAULT NULL,
  `permissions` json DEFAULT NULL,
  `access_level` varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT 'read',
  `created_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uc_agent_org` (`agent_id`,`org_id`),
  KEY `fk_aor_org` (`org_id`),
  CONSTRAINT `fk_aor_agent` FOREIGN KEY (`agent_id`) REFERENCES `agents` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT,
  CONSTRAINT `fk_aor_org` FOREIGN KEY (`org_id`) REFERENCES `agent_orgs` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
