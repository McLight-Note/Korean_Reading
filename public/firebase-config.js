/* Cloud sync (optional). Leave `null` to keep every visitor's data in their own browser only.
   To enable sign-in + sync, create a Firebase project and paste its web-app config here (see FIREBASE.md).
   These values are public identifiers, not secrets: access is enforced by firestore.rules.

   window.KR_FIREBASE = {
     apiKey: "...", authDomain: "your-project.firebaseapp.com", projectId: "your-project", appId: "..."
   };
*/
/* `|| null` lets a test or dev page define window.KR_FIREBASE before this file runs. */
window.KR_FIREBASE = window.KR_FIREBASE || null;
