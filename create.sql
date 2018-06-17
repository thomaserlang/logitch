CREATE SCHEMA IF NOT EXISTS `logitch` DEFAULT CHARACTER SET utf8mb4 ;
USE `logitch` ;

CREATE TABLE IF NOT EXISTS `logitch`.`entries` (
  `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `type` INT(2) NULL,
  `created_at` DATETIME NULL,
  `channel` VARCHAR(45) NULL,
  `room_id` INT UNSIGNED NULL,
  `user` VARCHAR(45) NULL,
  `user_id` INT UNSIGNED NULL,
  `message` TEXT NULL,
  `word_count` INT UNSIGNED NULL,
  PRIMARY KEY (`id`),
  INDEX `ix_entries_channel_user_type` (`channel` ASC, `user` ASC, `type` ASC),
  INDEX `ix_entries_channel_user_id_type_created_at` (`channel` ASC, `user_id` ASC, `type` ASC, `created_at` ASC),
  INDEX `ix_entries_channel_created_at` (`channel` ASC, `created_at` ASC))
ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS `logitch`.`usernames` (
  `user_id` INT UNSIGNED NOT NULL,
  `user` VARCHAR(45) NOT NULL,
  PRIMARY KEY (`user_id`, `user`))
ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS `logitch`.`user_stats` (
  `channel` VARCHAR(45) NOT NULL,
  `user_id` INT NOT NULL,
  `bans` INT(3) UNSIGNED NULL DEFAULT 0,
  `timeouts` INT(3) UNSIGNED NULL DEFAULT 0,
  `purges` INT(3) NULL DEFAULT 0,
  `chat_messages` INT NULL DEFAULT 0,
  PRIMARY KEY (`user_id`, `channel`))
ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS `logitch`.`modlogs` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `created_at` DATETIME NULL,
  `channel` VARCHAR(45) NULL,
  `user_id` INT NULL,
  `user` VARCHAR(45) NULL,
  `command` VARCHAR(45) NULL,
  `args` VARCHAR(500) NULL,
  `target_user` VARCHAR(45) NULL,
  `target_user_id` INT NULL,
  PRIMARY KEY (`id`),
  INDEX `ix_modlogs_channel_user` (`channel` ASC, `user` ASC))
ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS `logitch`.`mods` (
  `channel` VARCHAR(45) NOT NULL,
  `user_id` INT NOT NULL,
  `user` VARCHAR(45) NULL,
  PRIMARY KEY (`channel`, `user_id`))
ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS `logitch`.`discord_entries` (
  `id` VARCHAR(30) NOT NULL,
  `server_id` VARCHAR(30) NULL,
  `channel_id` VARCHAR(30) NULL,
  `created_at` DATETIME NULL,
  `updated_at` DATETIME NULL,
  `message` TEXT NULL,
  `attachments` TEXT NULL,
  `user` VARCHAR(32) NULL,
  `user_id` VARCHAR(30) NULL,
  `user_discriminator` VARCHAR(10) NULL,
  `deleted` ENUM('Y', 'N') NULL DEFAULT 'N',
  `deleted_at` DATETIME NULL,
  PRIMARY KEY (`id`))
ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS `logitch`.`discord_entry_versions` (
  `id` INT(11) UNSIGNED NOT NULL AUTO_INCREMENT,
  `entry_id` VARCHAR(30) NULL,
  `created_at` DATETIME NULL,
  `message` TEXT NULL,
  `attachments` TEXT NULL,
  PRIMARY KEY (`id`))
ENGINE = InnoDB;

USE `logitch`;

DELIMITER $$
USE `logitch`$$
CREATE DEFINER = CURRENT_USER TRIGGER `logitch`.`entries_AFTER_INSERT` AFTER INSERT ON `entries` FOR EACH ROW
BEGIN
	INSERT IGNORE INTO usernames (user_id, user) VALUES (new.user_id, new.user);
    CASE
		WHEN new.`type` = 1 THEN
        BEGIN
			insert into user_stats (channel, user_id, chat_messages) VALUES (new.channel, new.user_id, 1) ON DUPLICATE KEY UPDATE chat_messages=chat_messages+1;
		END;
		WHEN new.`type` = 2 THEN insert into user_stats (channel, user_id, bans) VALUES (new.channel, new.user_id, 1) ON DUPLICATE KEY UPDATE bans=bans+1;
        WHEN new.`type` = 3 THEN insert into user_stats (channel, user_id, timeouts) VALUES (new.channel, new.user_id, 1) ON DUPLICATE KEY UPDATE timeouts=timeouts+1;
        WHEN new.`type` = 4 THEN insert into user_stats (channel, user_id, purges) VALUES (new.channel, new.user_id, 1) ON DUPLICATE KEY UPDATE purges=purges+1;
		ELSE BEGIN END;
    END CASE;
END$$


DELIMITER ;
