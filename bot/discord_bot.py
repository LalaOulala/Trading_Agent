from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.config import BotConfig
from bot.reporting import build_hourly_report, split_discord_message


logger = logging.getLogger(__name__)


class TradingDiscordBot(commands.Bot):
    def __init__(self, config: BotConfig) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.config = config
        self._commands_registered = False

    async def setup_hook(self) -> None:
        if not self._commands_registered:
            self._register_commands()
            self._commands_registered = True

        await self.tree.sync()

        self.hourly_report_loop.change_interval(minutes=self.config.report_interval_minutes)
        if not self.hourly_report_loop.is_running():
            self.hourly_report_loop.start()

    def _register_commands(self) -> None:
        @self.tree.command(name="ping", description="Vérifie que le bot est en ligne.")
        async def ping(interaction: discord.Interaction) -> None:
            await interaction.response.send_message("pong", ephemeral=True)

        @self.tree.command(
            name="status",
            description="Envoie immédiatement un rapport trading/portefeuille/coûts API.",
        )
        async def status(interaction: discord.Interaction) -> None:
            await interaction.response.defer(ephemeral=True, thinking=True)
            await self._send_report(reason="manual_command")
            await interaction.followup.send("Rapport envoyé.", ephemeral=True)

    async def on_ready(self) -> None:
        user_tag = f"{self.user}" if self.user else "unknown"
        logger.info("Discord bot connecté: %s", user_tag)

    async def _resolve_channel(self) -> discord.abc.Messageable | None:
        if self.config.discord_channel_id is None:
            logger.warning("DISCORD_CHANNEL_ID absent: envoi horaire désactivé.")
            return None

        channel = self.get_channel(self.config.discord_channel_id)
        if channel is None:
            try:
                channel = await self.fetch_channel(self.config.discord_channel_id)
            except Exception as exc:
                logger.error(
                    "Impossible de récupérer le channel Discord %s: %s",
                    self.config.discord_channel_id,
                    exc,
                )
                return None

        if isinstance(channel, discord.abc.Messageable):
            return channel
        logger.error("Le channel %s n'est pas messageable.", self.config.discord_channel_id)
        return None

    async def _send_report(self, *, reason: str) -> None:
        channel = await self._resolve_channel()
        if channel is None:
            return

        report = build_hourly_report(self.config)
        messages = split_discord_message(report)
        if not messages:
            logger.warning("Rapport vide (reason=%s).", reason)
            return

        for chunk in messages:
            await channel.send(chunk)
        logger.info(
            "Rapport Discord envoyé (%s chunk(s), reason=%s).",
            len(messages),
            reason,
        )

    @tasks.loop(minutes=60)
    async def hourly_report_loop(self) -> None:
        await self._send_report(reason="scheduled")

    @hourly_report_loop.before_loop
    async def before_hourly_report_loop(self) -> None:
        await self.wait_until_ready()


def run_bot(config: BotConfig) -> None:
    if not config.discord_token:
        raise RuntimeError(
            "DISCORD_BOT_TOKEN manquant. Ajoute-le dans .env avant de lancer le bot."
        )

    bot = TradingDiscordBot(config)
    bot.run(config.discord_token)
