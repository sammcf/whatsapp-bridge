#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "$project_dir/scripts/setup-oauth.py"
quadlet_dir="$HOME/.config/containers/systemd"
unit_dir="$HOME/.config/systemd/user"
mkdir -p "$quadlet_dir" "$unit_dir"
for name in waha waha-proxy; do
    destination="$quadlet_dir/$name.container"
    # Replace only this project's old deployment links with boot-available copies.
    if [[ -L "$destination" ]]; then
        [[ "$(readlink -f -- "$destination")" == "$project_dir/deploy/$name.container" ]] || {
            echo "Refusing to replace unrelated symlink: $destination" >&2
            exit 1
        }
        rm -- "$destination"
    fi
    install -m 644 "$project_dir/deploy/$name.container" "$destination"
done
install -m 644 "$project_dir/deploy/waha-funnel.service" "$unit_dir/waha-funnel.service"
install -m 644 "$project_dir/deploy/waha-oauth.service" "$unit_dir/waha-oauth.service"
loginctl enable-linger "$(id -un)"
systemctl --user daemon-reload
systemctl --user enable --now waha-oauth.service
# Quadlet [Install] sections generate default.target dependencies automatically.
systemctl --user enable --now waha-funnel.service
systemctl --user start waha.service waha-proxy.service
