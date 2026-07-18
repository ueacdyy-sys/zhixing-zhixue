pluginManagement {
    repositories {
        google {
            content {
                includeGroupByRegex("com\\.android.*")
                includeGroupByRegex("com\\.google.*")
                includeGroupByRegex("androidx.*")
            }
        }
        mavenCentral()
        gradlePluginPortal()
    }
}
plugins {
    id("org.gradle.toolchains.foojay-resolver-convention") version "1.0.0"
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        // Verified artifacts downloaded through IDM are staged here first, so
        // offline builds never fall back to an uncontrolled network fetch.
        maven { url = uri("$rootDir/vendor-maven") }
        google()
        mavenCentral()
    }
}

enableFeaturePreview("TYPESAFE_PROJECT_ACCESSORS")

rootProject.name = "ZhixingZhixueMobile"

include(":app")
include(":common")
include(":mjpeg")
include(":rtsp")
include(":webrtc")
include(":learning-domain")
include(":learning-application")
include(":edge-android")
