export default function ConfirmModal({ message, onConfirm, onCancel, confirmLabel = 'Delete', cancelLabel = 'Cancel', danger = true }) {
  return (
    <div className="modal-overlay" style={{display:'flex'}} onClick={onCancel}>
      <div className="modal-box" onClick={e => e.stopPropagation()}>
        <div className={`modal-icon${danger ? '' : ' modal-icon-neutral'}`}>
          <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
          </svg>
        </div>
        <p className="modal-msg">{message}</p>
        <div className="modal-actions">
          <button className="btn btn-secondary" onClick={onCancel}>{cancelLabel}</button>
          <button className={`btn ${danger ? 'btn-danger' : 'btn-primary'}`} onClick={onConfirm}>{confirmLabel}</button>
        </div>
      </div>
    </div>
  )
}
