#include "service_7.h"

Service7::Service7() {}

void Service7::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service7::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
