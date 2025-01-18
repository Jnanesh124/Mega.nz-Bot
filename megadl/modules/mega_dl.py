import re
from os import path, makedirs
import time

from pyrogram import filters
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from megadl import CypherClient
from megadl.lib.megatools import MegaTools


@CypherClient.on_message(
    filters.regex(r"(https?:\/\/mega\.nz\/(file|folder|#)?.+)|(\/Root\/?.+)")
)
@CypherClient.run_checks
async def dl_from(client: CypherClient, msg: Message):
    # Push info to temp db
    _mid = msg.id
    _usr = msg.from_user.id
    client.glob_tmp[_usr] = [msg.text, f"{client.dl_loc}/{_usr}"]
    await msg.reply(
        "**Select what you want to do 🤗**",
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Download 💾", callback_data=f"dwn_mg-{_mid}")],
                [InlineKeyboardButton("Info ℹ️", callback_data=f"info_mg-{_mid}")],
                [InlineKeyboardButton("Cancel ❌", callback_data=f"cancelqcb-{_usr}")],
            ]
        ),
    )


prv_rgx = r"(\/Root\/?.+)"


@CypherClient.on_callback_query(filters.regex(r"dwn_mg?.+"))
@CypherClient.run_checks
async def dl_from_cb(client: CypherClient, query: CallbackQuery):
    # Access saved info
    _mid = int(query.data.split("-")[1])
    qcid = query.message.chat.id
    qusr = query.from_user.id
    dtmp = client.glob_tmp.get(qusr)
    url = dtmp[0]
    dlid = dtmp[1]

    # weird workaround to add support for private mode
    conf = None
    if client.is_public:
        udoc = await client.database.is_there(qusr, True)
        if not udoc and re.match(prv_rgx, url):
            return await query.edit_message_text(
                "`You must be logged in first to download this file 😑`"
            )
        if udoc:
            email = client.cipher.decrypt(udoc["email"]).decode()
            password = client.cipher.decrypt(udoc["password"]).decode()
            proxy = f"--proxy {udoc['proxy']}" if udoc["proxy"] else ""
            conf = f"--username {email} --password {password} {proxy}"

    # Create unique download folder
    if not path.isdir(dlid):
        makedirs(dlid)

    # Download the file/folder
    resp = await query.edit_message_text(
        "`Your download is starting 📥...`", reply_markup=None
    )

    cli = MegaTools(client, conf)

    f_list = None

    # Track the download progress with periodic updates
    last_time = time.time()  # To track time for speed calculation
    last_bytes = 0  # To track how many bytes were downloaded in the last period
    progress_message = None  # The message that will show progress

    async def update_progress(downloaded_bytes, total_bytes):
        nonlocal last_time, last_bytes, progress_message
        elapsed_time = time.time() - last_time

        if elapsed_time > 1:  # Update every 1 second
            download_speed = (downloaded_bytes - last_bytes) / elapsed_time  # bytes per second
            download_progress = (downloaded_bytes / total_bytes) * 100  # Percentage of completion

            speed_str = f"{download_speed / 1024:.2f} KB/s"  # Convert bytes to KB
            progress_str = f"{download_progress:.2f}%"

            # Update the message with live progress
            if progress_message:
                await progress_message.edit(
                    text=f"`Download Progress: {progress_str}`\n`Speed: {speed_str}`"
                )
            else:
                progress_message = await query.edit_message_text(
                    text=f"`Download Progress: {progress_str}`\n`Speed: {speed_str}`"
                )

            # Update last time and bytes
            last_time = time.time()
            last_bytes = downloaded_bytes

    # Download the file/folder with live progress updates
    f_list = await cli.download(
        url,
        qusr,
        qcid,
        resp.id,
        path=dlid,
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Cancel ❌", callback_data=f"cancelqcb-{qusr}")],
            ]
        ),
        progress_callback=update_progress  # Pass the progress callback function
    )

    if not f_list:
        return

    await query.edit_message_text("`Successfully downloaded the content 🥳`")
    # Update download count
    if client.database:
        await client.database.plus_fl_count(qusr, downloads=len(f_list))
    
    # Send file(s) to the user
    await resp.edit("`Trying to upload now 📤...`")
    await client.send_files(
        f_list,
        qcid,
        resp.id,
        reply_to_message_id=_mid,
        caption=f"**Join @NexaBotsUpdates ❤️**",
    )
    await client.full_cleanup(dlid, qusr)
    await resp.delete()

