#include "service_20.h"

Service20::Service20() {}

void Service20::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service20::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
