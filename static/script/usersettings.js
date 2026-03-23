
document.addEventListener("DOMContentLoaded", () => {
  const uploadBtn = document.getElementById("avatarbutton");
  const fileInput = document.getElementById("avatarupload");

  uploadBtn.addEventListener("click", () => {
    fileInput.click();
  });

  fileInput.addEventListener("change", () => {
    if (fileInput.files.length > 0) {
      console.log("Selected file:", fileInput.files[0]);
    }
  });
});