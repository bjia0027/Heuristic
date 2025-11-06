#include "service_18.h"

Service18::Service18() {}

void Service18::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service18::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
