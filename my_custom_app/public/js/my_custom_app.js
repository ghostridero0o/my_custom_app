(() => {
	const NAVBAR_CONFIG = {
		mode: "image",
		color: "#22c55e",
		image: "/assets/my_custom_app/images/navbar.jpg",
		textColor: "#ffd900",
		overlay: "rgba(0, 0, 0, 0.18)",
	};

	function applyNavbarStyle() {
		const root = document.documentElement;
		const navbar = document.querySelector("header.navbar");
		if (!navbar) return;

		const isImageMode = NAVBAR_CONFIG.mode === "image";

		root.style.setProperty("--custom-navbar-color", NAVBAR_CONFIG.color);
		root.style.setProperty("--custom-navbar-text-color", NAVBAR_CONFIG.textColor);
		root.style.setProperty("--custom-navbar-overlay", isImageMode ? NAVBAR_CONFIG.overlay : "transparent");
		root.style.setProperty(
			"--custom-navbar-image",
			isImageMode ? `url("${NAVBAR_CONFIG.image}")` : "none"
		);

		navbar.setAttribute("data-custom-navbar-mode", NAVBAR_CONFIG.mode);
		navbar.style.setProperty("border-bottom", "none", "important");
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", applyNavbarStyle);
	} else {
		applyNavbarStyle();
	}

	const observer = new MutationObserver(() => applyNavbarStyle());
	observer.observe(document.documentElement, {
		childList: true,
		subtree: true,
	});
})();
