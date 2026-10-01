import { useCallback, useEffect, useState } from "react";
import { axios } from "@/services/axios";
import { currentUser } from "@/services/auth";
import notification from "@/services/notification";
import ConfirmQueryDialog from "@/components/queries/ConfirmQueryDialog";

/*
  Confirming a saved query as the right answer to a question.

  The strongest thing the catalog carries, and the only part of it a person
  has to supply: a measure can be mined out of saved SQL, but "this whole
  question is answered correctly here" cannot. So the control lives where the
  SQL is on screen -- confirming from a list would be signing a document
  nobody opened.

  The server records the hash of the text that was read. Editing the query
  afterwards leaves the confirmation in place but stops it counting anywhere,
  and the Catalog page is where that gets noticed; see `still_current`.
*/
export default function useVerifyQuery(query) {
  const canVerify = currentUser.can("manage_catalog");
  const [verification, setVerification] = useState(null);
  const id = query && query.id;

  useEffect(() => {
    if (!canVerify || !id) {
      return undefined;
    }
    let live = true;
    axios
      .get(`/api/catalog/queries/${id}`)
      .then((data) => {
        if (live) {
          setVerification(data.verified ? data : null);
        }
      })
      // Silent: a page that cannot answer "is this confirmed" should not
      // interrupt somebody who came here to read a query.
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [canVerify, id]);

  const confirm = useCallback(() => {
    ConfirmQueryDialog.showModal({ query, verification }).onClose((values) =>
      axios
        .post(`/api/catalog/queries/${id}`, values)
        .then((saved) => {
          setVerification(saved);
          notification.success("Confirmed as the right answer.");
        })
        .catch(() => notification.error("Could not save that."))
    );
  }, [id, query, verification]);

  const withdraw = useCallback(
    () =>
      axios
        .delete(`/api/catalog/queries/${id}`)
        .then(() => {
          setVerification(null);
          notification.success("No longer confirmed.");
        })
        .catch(() => notification.error("Could not save that.")),
    [id]
  );

  return { canVerify, verification, confirm, withdraw };
}
