sudo systemctl status camera_server.service
sudo systemctl start camera_server.service
sudo systemctl enable camera_server.service
sudo systemctl stop camera_server.service
sudo systemctl disable camera_server.service

sudo journalctl -u camera_server.service -n 500 -f

