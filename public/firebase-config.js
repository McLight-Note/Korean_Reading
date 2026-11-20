//Your Firebase settings. The stories and the read lists are stored in Firebase, so this must be filled in
  // (README, Part 3d). These values are public identifiers, not secrets: access is enforced by firestore.rules.

   window.KR_FIREBASE = firebaseConfig = {
apiKey: "AIzaSyCFJCEiwp-7olpfFsm29Tu7_KciiA7uxBg",
authDomain: "korean-reading.firebaseapp.com",
projectId: "korean-reading",
storageBucket: "korean-reading.firebasestorage.app",
messagingSenderId: "1018613040856",
appId: "1:1018613040856:web:9d61b553e72823d71379ad",
measurementId: "G-4T8NHJTR3C"
};

/* `|| null` lets a test define window.KR_FIREBASE before this file runs. */
window.KR_FIREBASE = window.KR_FIREBASE || null;
