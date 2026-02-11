import type { NextApiRequest, NextApiResponse } from 'next';
import formidable from 'formidable';
import fs from 'fs';
import axios from 'axios';

// Disable default body parser to handle file upload manually
export const config = {
  api: {
    bodyParser: false,
  },
};

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    // 1. Parse the uploaded file
    const form = formidable({});
    const [fields, files] = await form.parse(req);
    
    const fileField = files.file;
    const uploadedFile = Array.isArray(fileField) ? fileField[0] : fileField;
    if (!uploadedFile) {
        return res.status(400).json({ error: 'No file uploaded' });
    }

    // 2. Read file to Base64
    const fileContent = fs.readFileSync(uploadedFile.filepath);
    const base64Data = fileContent.toString('base64');

    // 3. Send to Google Apps Script
    // Using x-www-form-urlencoded as Apps Script parameters usually expect that or FormData
    const scriptUrl = 'https://script.google.com/macros/s/AKfycbzej-b7N82mzY7neub-THVIhbwHtp_furowzp5eghwbCoHD_BaAnUZjcLKOdfO28xlQPA/exec';
    
    // Google Apps Script doPost parameters can be tricky. Often it's best to send JSON body 
    // but the script provided uses e.parameter.fileContent which implies URL query params or form data.
    // However, sending large base64 in URL params is bad.
    // Let's assume the script handles POST body payload if we adapt it or check provided script.
    
    // The user provided script uses e.parameter which comes from query string or x-www-form-urlencoded body.
    // We will send specific form data.
    const formData = new URLSearchParams();
    formData.append('fileName', uploadedFile.originalFilename || 'budget.xlsx');
    formData.append('fileContent', base64Data);

    // Note: Apps Script redirect handling. Axios follows redirects by default.
    const response = await axios.post(scriptUrl, formData, {
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
    });
    
    // Apps Script usually returns 200/302.
    // And returns JSON { status: 'success', sheetId: '...' }
    
    if (response.data?.status === 'success' && response.data?.sheetId) {
         // Construct webViewLink manually or fetch if needed. Usually:
         const webViewLink = `https://docs.google.com/spreadsheets/d/${response.data.sheetId}/edit`;
         
         return res.status(200).json({ 
            link: webViewLink, 
            id: response.data.sheetId 
         });
    } else if (response.data?.status === 'error') {
        throw new Error(response.data.message);
    } else {
        // Sometimes Apps Script returns HTML with redirect or confirmation
        // But ContentService.createTextOutput().setMimeType(JSON) should return JSON.
        console.log("Apps Script response:", response.data);
        // If it's a specific format error, we handle it
        throw new Error('Unknown response from Google Apps Script');
    }

  } catch (error: any) {
    console.error('GAS upload error:', error);
    return res.status(500).json({ error: error.message });
  }
}


