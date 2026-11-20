/* Your Firebase settings. The stories and the read lists are stored in Firebase, so this must be filled in
   (README, Part 3d). These values are public identifiers, not secrets: access is enforced by firestore.rules.

   window.KR_FIREBASE = {
     apiKey: "...", authDomain: "your-project.firebaseapp.com", projectId: "your-project", appId: "..."
   };
*/
/* `|| null` lets a test define window.KR_FIREBASE before this file runs. */
window.KR_FIREBASE = window.KR_FIREBASE || null;
