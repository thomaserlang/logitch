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
  INDEX `ix_entries_channel_user` (`channel` ASC, `user` ASC, `type` ASC))
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


-- -----------------------------------------------------
-- Table `logitch`.`modlogs`
-- -----------------------------------------------------
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


-- -----------------------------------------------------
-- Table `logitch`.`mods`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `logitch`.`mods` (
  `channel` VARCHAR(45) NOT NULL,
  `user_id` INT NOT NULL,
  `user` VARCHAR(45) NULL,
  PRIMARY KEY (`channel`, `user_id`))
ENGINE = InnoDB;

USE `logitch`;

DELIMITER $$
USE `logitch`$$
CREATE DEFINER = CURRENT_USER TRIGGER `logitch`.`entries_AFTER_INSERT` AFTER INSERT ON `entries` FOR EACH ROW
BEGIN
    CASE
		WHEN new.`type` = 1 THEN
        BEGIN
			INSERT IGNORE INTO usernames (user_id, user) VALUES (new.user_id, new.user);
			insert into user_stats (channel, user_id, chat_messages) VALUES (new.channel, new.user_id, 1) ON DUPLICATE KEY UPDATE chat_messages=chat_messages+1;
		END;
		WHEN new.`type` = 2 THEN insert into user_stats (channel, user_id, bans) VALUES (new.channel, new.user_id, 1) ON DUPLICATE KEY UPDATE bans=bans+1;
        WHEN new.`type` = 3 THEN insert into user_stats (channel, user_id, timeouts) VALUES (new.channel, new.user_id, 1) ON DUPLICATE KEY UPDATE timeouts=timeouts+1;
        WHEN new.`type` = 4 THEN insert into user_stats (channel, user_id, purges) VALUES (new.channel, new.user_id, 1) ON DUPLICATE KEY UPDATE purges=purges+1;
		ELSE BEGIN END;
    END CASE;
END$$


DELIMITER ;

SET SQL_MODE=@OLD_SQL_MODE;
SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS;
SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS;
