############################
# DOCKER-RELATED FUNCTIONS #
############################

########
pull_docker_img()
{
    local img_name=$1

    if ! docker_img_exists "${img_name}"; then
        "${DOCKER}" pull "${img_name}" || return 1
    fi
}

########
docker_img_exists()
{
    local img_name=$1

    if "${DOCKER}" image inspect "${img_name}" > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}
