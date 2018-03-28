SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0;
SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0;
SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='TRADITIONAL,ALLOW_INVALID_DATES';

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
  PRIMARY KEY (`id`),
  INDEX `ix_entries_channel_user` (`channel` ASC, `user` ASC, `type` ASC))
ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS `logitch`.`usernames` (
  `user_id` INT UNSIGNED NOT NULL,
  `user` VARCHAR(45) NULL,
  PRIMARY KEY (`user_id`))
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
