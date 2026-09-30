/*
  Which of the alert page's three faces to show.

  Its own module so `alerts.routes.jsx` can name a mode without importing the
  page -- the point of that file being that the page is not in the first
  download.
*/
const MODES = {
  NEW: 0,
  VIEW: 1,
  EDIT: 2,
};

export default MODES;
