const { google } = require('googleapis');
const fs = require('fs');
const path = require('path');

async function checkFolder() {
  try {
    const envPath = path.join(__dirname, '.env.local');
    const envContent = fs.readFileSync(envPath, 'utf8');
    
    // Manual parse
    const client_email = envContent.match(/GOOGLE_CLIENT_EMAIL="([^"]+)"/)[1];
    const private_key = envContent.match(/GOOGLE_PRIVATE_KEY="((?:[^"\\]|\\.)+)"/)[1].replace(/\\n/g, '\n');
    const folderId = envContent.match(/GOOGLE_DRIVE_FOLDER_ID="([^"]+)"/)?.[1];

    console.log(`Checking folder: ${folderId}`);
    console.log(`Service Account: ${client_email}`);

    const auth = new google.auth.GoogleAuth({
      credentials: { client_email, private_key },
      scopes: ['https://www.googleapis.com/auth/drive'],
    });

    const drive = google.drive({ version: 'v3', auth });

    try {
        const file = await drive.files.get({
            fileId: folderId,
            fields: 'id, name, owners, capabilities, permissions, driveId',
            supportsAllDrives: true
        });
        
        console.log("Folder Name:", file.data.name);
        console.log("Is on Shared Drive (driveId present):", !!file.data.driveId);
        console.log("Can Add Children:", file.data.capabilities.canAddChildren);
        console.log("Owners:", JSON.stringify(file.data.owners));
        
    } catch (e) {
        console.error("Error accessing folder:", e.message);
    }
    
    // Try to create a small test file
    try {
        console.log("Attempting to create a test file...");
        const res = await drive.files.create({
            requestBody: {
                name: 'test_quota_check.txt',
                parents: [folderId]
            },
            media: {
                mimeType: 'text/plain',
                body: 'Hello World'
            },
            supportsAllDrives: true
        });
        console.log("Success! File ID:", res.data.id);
        // Clean up
        await drive.files.delete({ fileId: res.data.id });
    } catch (e) {
        console.error("Creation Failed:", e.message);
    }

  } catch (error) {
    console.error('Script Error:', error);
  }
}

checkFolder();
