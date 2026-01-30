const BSKY_HANDLE = 'yourhandle.bsky.social'; // Your full handle
const APP_PASSWORD = 'xxxx-xxxx-xxxx-xxxx'; // Your generated App Password
const SHEET_ID = "your-sheet-id";//Google sheet id
const SHEET_NAMES = [
    "Peak Share",
    "Peak Generation"
]

var today = new Date();
// Normalize today's date to midnight to ignore time differences
today.setHours(0, 0, 0, 0);

function postToBluesky() {
    // Targets the specific file by ID and the specific tab by Name
    const ss = SpreadsheetApp.openById(SHEET_ID);

    // 1. Authenticate and get a session token
    const authResponse = UrlFetchApp.fetch("https://bsky.social/xrpc/com.atproto.server.createSession", {
        method: "POST",
        contentType: "application/json",
        payload: JSON.stringify({ identifier: BSKY_HANDLE, password: APP_PASSWORD })
    });
    const session = JSON.parse(authResponse.getContentText());
    const token = session.accessJwt;
    const did = session.did;

    // 2. Loop through each sheet
    for (const sheetName of SHEET_NAMES) {
        Logger.log("Searching for posts in " + sheetName);
        sheet = ss.getSheetByName(sheetName);
        data = sheet.getDataRange().getValues();

        // 3. Loop through rows to find content to post
        for (let i = 1; i < data.length; i++) {
            if (shouldPost(data, i)) {
                let content = data[i][8]; // Assuming Column I is Post Content
                let row_number = i + 1;   // Note that sheet ranges start a 1, while the data array is 0-indexed
                Logger.log("Posting row " + row_number);
                try {
                    const postRecord = {
                        repo: did,
                        collection: "app.bsky.feed.post",
                        record: {
                            "$type": "app.bsky.feed.post",
                            "text": content,
                            "createdAt": new Date().toISOString()
                        }
                    };

                    UrlFetchApp.fetch("https://bsky.social/xrpc/com.atproto.repo.createRecord", {
                        method: "POST",
                        headers: { "Authorization": "Bearer " + token },
                        contentType: "application/json",
                        payload: JSON.stringify(postRecord)
                    });

                    sheet.getRange(row_number, 1).setValue("Posted");
                } catch (e) {
                    Logger.log("Error posting row " + row_number + ": " + e.toString());
                }
            }
        }
    }
}

function shouldPost(data, row) {
    let content = data[row][8];              // Column I is Post Content
    let status = data[row][0];               // Column A is Status
    let rowDate = new Date(data[row][1]);    // Column B contains the date to post
    rowDate.setHours(0, 0, 0, 0);
    return content && status == "Ready" && rowDate <= today
}


