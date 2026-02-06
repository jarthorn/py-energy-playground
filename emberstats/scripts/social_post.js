const BSKY_HANDLE = ''; // Your full handle
const BSKY_APP_PASSWORD = ''; // Your generated App Password

const X_CLIENT_ID = '';     //OAuth2 client id
const X_CLIENT_SECRET = ''; //OAuth2 client secret
const X_URL = 'https://api.x.com/2/tweets'

const SHEET_ID = '';//Google sheet id
const SHEET_NAMES = [
    "Peak Share",
    "Peak Generation"
]

var today = new Date();
// Normalize today's date to midnight to ignore time differences
today.setHours(0, 0, 0, 0);

function postToSocials() {
    // Targets the specific file by ID and the specific tab by Name
    const ss = SpreadsheetApp.openById(SHEET_ID);

    // 1. Authenticate and get a session token
    const authResponse = UrlFetchApp.fetch("https://bsky.social/xrpc/com.atproto.server.createSession", {
        method: "POST",
        contentType: "application/json",
        payload: JSON.stringify({ identifier: BSKY_HANDLE, password: BSKY_APP_PASSWORD })
    });
    const session = JSON.parse(authResponse.getContentText());
    const token = session.accessJwt;
    const did = session.did;

    const twitterService = getTwitterService_();

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
                    postBluesky(content, token, did);
                } catch (e) {
                    Logger.log("Error posting to BlueSky row " + row_number + ": " + e.toString());
                }
                try {
                    postTwitter(content, twitterService);
                } catch (e) {
                    Logger.log("Error posting to Twitter row " + row_number + ": " + e.toString());
                }
                sheet.getRange(row_number, 1).setValue("Posted");
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

function postBluesky(content, token, did) {
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
}

function postTwitter(content, twitterService) {
    if (twitterService.hasAccess()) {
        var response = UrlFetchApp.fetch(X_URL, {
            method: 'POST',
            'contentType': 'application/json',
            headers: {
                Authorization: 'Bearer ' + twitterService.getAccessToken()
            },
            muteHttpExceptions: false,
            payload: JSON.stringify({
                text: content
            })
        });
        var result = JSON.parse(response.getContentText());
        Logger.log(JSON.stringify(result, null, 2));
    } else {
        const authorizationUrl = twitterService.getAuthorizationUrl();
        Logger.log('Open the following URL and re-run the script: %s', authorizationUrl);
    }
}

function getTwitterService_() {
    pkceChallengeVerifier();
    const userProps = PropertiesService.getUserProperties();
    const scriptProps = PropertiesService.getScriptProperties();
    return OAuth2.createService('twitter')
        .setAuthorizationBaseUrl('https://twitter.com/i/oauth2/authorize')
        .setTokenUrl('https://api.twitter.com/2/oauth2/token?code_verifier=' + userProps.getProperty("code_verifier"))
        .setClientId(X_CLIENT_ID)
        .setClientSecret(X_CLIENT_SECRET)
        .setCallbackFunction('authCallback')
        .setPropertyStore(userProps)
        .setScope('users.read tweet.read tweet.write offline.access')
        .setParam('response_type', 'code')
        .setParam('code_challenge_method', 'S256')
        .setParam('code_challenge', userProps.getProperty("code_challenge"))
        .setTokenHeaders({
            'Authorization': 'Basic ' + Utilities.base64Encode(X_CLIENT_ID + ':' + X_CLIENT_SECRET),
            'Content-Type': 'application/x-www-form-urlencoded'
        })
}

function authCallback(request) {
    const service = getTwitterService_();
    const authorized = service.handleCallback(request);
    if (authorized) {
        return HtmlService.createHtmlOutput('Success!');
    } else {
        return HtmlService.createHtmlOutput('Denied.');
    }
}

function pkceChallengeVerifier() {
    var userProps = PropertiesService.getUserProperties();
    if (!userProps.getProperty("code_verifier")) {
        var verifier = "";
        var possible = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~";

        for (var i = 0; i < 128; i++) {
            verifier += possible.charAt(Math.floor(Math.random() * possible.length));
        }

        var sha256Hash = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, verifier)

        var challenge = Utilities.base64Encode(sha256Hash)
            .replace(/\+/g, '-')
            .replace(/\//g, '_')
            .replace(/=+$/, '')
        userProps.setProperty("code_verifier", verifier)
        userProps.setProperty("code_challenge", challenge)
    }
}

