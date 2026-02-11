const { google } = require('googleapis');
const fs = require('fs');
const path = require('path');

async function cleanDrive() {
  try {
    // Manually read credentials from .env.local to avoid dotenv parsing issues if any
    const envPath = path.join(__dirname, '.env.local');
    const envContent = fs.readFileSync(envPath, 'utf8');
    
    // Simple regex parse for the specific keys we need
    const emailMatch = envContent.match(/GOOGLE_CLIENT_EMAIL="([^"]+)"/);
    const keyMatch = envContent.match(/GOOGLE_PRIVATE_KEY="((?:[^"\\]|\\.)+)"/);

    if (!emailMatch || !keyMatch) {
      console.error("Could not find credentials in .env.local");
      process.exit(1);
    }

    const client_email = emailMatch[1];
    const private_key = keyMatch[1].replace(/\\n/g, '\n');

    const auth = new google.auth.GoogleAuth({
      credentials: {
        client_email,
        private_key,
      },
      scopes: ['https://www.googleapis.com/auth/drive'],
    });

    const drive = google.drive({ version: 'v3', auth });

    try {
        console.log("Emptying trash...");
        await drive.files.emptyTrash();
        console.log("Trash emptied.");
    } catch (e) {
        console.error("Error emptying trash:", e.message);
    }
    
    console.log("Checking quota...");
    try {
        const about = await drive.about.get({ fields: 'storageQuota' });
        console.log("Quota:", about.data.storageQuota);
    } catch (e) {
        console.error("Error checking quota:", e.message);
    }

    console.log("Listing files(including trashed)...");
    const res = await drive.files.list({
      pageSize: 100,
      fields: 'nextPageToken, files(id, name, createdTime, trashed, size)',
      q: "trashed = true or trashed = false" // List everything
    });

    const files = res.data.files;
    if (files.length) {
      console.log(`Found ${files.length} files. Deleting...`);
      for (const file of files) {
        console.log(`Deleting file: ${file.name} (${file.id})`);
        try {
            await drive.files.delete({ fileId: file.id });
        } catch (e) {
            console.error(`Failed to delete ${file.id}: ${e.message}`);
        }
      }
      console.log('Cleanup complete.');
    } else {
      console.log('No files found.');
    }
  } catch (error) {
    console.error('Error:', error);
  }
}

cleanDrive();
