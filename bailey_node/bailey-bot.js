const {
  default: makeWASocket,
  useMultiFileAuthState,
  fetchLatestBaileysVersion,
  DisconnectReason,
} = require("@whiskeysockets/baileys");
const axios = require("axios");
const { Boom } = require("@hapi/boom");
const pino = require("pino");
const qrcode = require("qrcode-terminal");

async function start() {
  // Use the new multi-file auth state instead of single file
  const { state, saveCreds } = await useMultiFileAuthState("./auth_info");

  const { version } = await fetchLatestBaileysVersion();

  const sock = makeWASocket({
    version,
    auth: state,
    logger: pino({ level: "silent" }), // Reduce log noise
  });

  // Handle credentials update
  sock.ev.on("creds.update", saveCreds);

  // Handle connection updates
  sock.ev.on("connection.update", (update) => {
    const { connection, lastDisconnect, qr } = update;

    // Display QR code when available
    if (qr) {
      console.log("Scan this QR code with WhatsApp:");
      qrcode.generate(qr, { small: true });
    }

    if (connection === "close") {
      const shouldReconnect =
        lastDisconnect?.error?.output?.statusCode !==
        DisconnectReason.loggedOut;

      console.log("Connection closed due to:", lastDisconnect?.error);

      if (shouldReconnect) {
        console.log("Reconnecting...");
        start();
      }
    } else if (connection === "open") {
      console.log("WhatsApp connection opened successfully!");
    }
  });

  // Handle incoming messages
  sock.ev.on("messages.upsert", async ({ messages }) => {
    const msg = messages[0];
    if (!msg.message || msg.key.fromMe) return;

    const sender = msg.key.remoteJid;
    const text =
      msg.message.conversation ||
      msg.message.extendedTextMessage?.text ||
      msg.message.imageMessage?.caption ||
      msg.message.videoMessage?.caption;

    if (!text) return;

    console.log(`Received message from ${sender}: ${text}`);

    try {
      const res = await axios.post(
        "http://127.0.0.1:8000/ask",
        new URLSearchParams({ question: text }),
        {
          headers: {
            "Content-Type": "application/x-www-form-urlencoded",
          },
          timeout: 30000, // 30 second timeout
        }
      );

      const answer = res.data.answer || "Jawaban tidak tersedia.";
      await sock.sendMessage(sender, { text: answer });
      console.log(`Sent reply to ${sender}: ${answer}`);
    } catch (err) {
      console.error("Error processing message:", err.message);
      await sock.sendMessage(sender, {
        text: "❌ Terjadi kesalahan saat menjawab pertanyaan Anda.",
      });
    }
  });
}

// Start the bot
start().catch((err) => {
  console.error("Failed to start bot:", err);
});
